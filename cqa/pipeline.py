"""The full pipeline: recording on disk -> report. No Streamlit here; progress goes through a callback.

prepare (one ffmpeg pass) + frames -> delete video -> Observer chunks in parallel -> redact -> merge
-> metrics -> leak test -> Judge -> label + confidence -> leak test -> report.
Heard names live only in memory inside run(); they are dropped before it returns.
"""
from __future__ import annotations

import json
import math
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import config, gemini, judge, media, merge, metrics, observer, privacy, quality, vtt
from .media import ffmpeg_exe
from .quality import ts

PARALLEL_CHUNKS = 4
Progress = Callable[[str, float, str], None]  # (step, fraction 0-1, message)


class PrivacyCheckFailed(RuntimeError):
    pass


def _cut_audio_copy(audio: Path, ch: observer.Chunk, out: Path) -> Path:
    """Chunk the already-extracted Observer audio without re-encoding it."""
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{ch.clip[0]:.3f}",
                    "-t", f"{ch.clip_len:.3f}", "-i", str(audio), "-c", "copy", str(out)], check=True)
    return out


def _grab_all_frames(src: Path, duration_s: float, out_dir: Path) -> list[tuple[float, Path]]:
    times = [60.0 * k for k in range(int(math.ceil(duration_s / 60)))]

    def grab(t: float) -> tuple[float, Path] | None:
        p = out_dir / f"f{int(t):05d}.jpg"
        subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src),
                        "-frames:v", "1", "-vf", f"scale={observer.FRAME_WIDTH}:-2", "-q:v", "5", str(p)])
        return (t, p) if p.exists() else None

    with ThreadPoolExecutor(4) as pool:
        return [f for f in pool.map(grab, times) if f]


def _observe_chunk(audio: Path, ch: observer.Chunk, frames, work: Path) -> gemini.Result:
    clip = _cut_audio_copy(audio, ch, work / f"chunk{ch.i:02d}.m4a")
    mine = [(t, p) for t, p in frames if ch.clip[0] <= t < ch.clip[1]]
    last_err = None
    for attempt in range(2):  # one retry on API errors (rate limits, timeouts)
        try:
            return observer.observe(clip, ch, mine)
        except Exception as e:  # noqa: BLE001 - any API failure marks the chunk failed after the retry
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"chunk {ch.i} failed: {type(last_err).__name__}")


def run(src: Path, work: Path, vtt_text: str | None = None, progress: Progress | None = None,
        delete_source: bool = True) -> dict:
    say = progress or (lambda *a: None)
    t0 = time.time()
    timings = {}
    labels = sorted({c.speaker for c in vtt.parse_text(vtt_text) if c.speaker}) if vtt_text else []

    # 1. prepare: audio + measurements (main thread) while frames are grabbed (background)
    info = media.probe(src)
    if not info.has_audio:
        raise ValueError("The file has no audio track.")
    frames_dir = work / "frames"
    frames_dir.mkdir(exist_ok=True)
    with ThreadPoolExecutor(1) as bg:
        fut_frames = bg.submit(_grab_all_frames, src, info.duration_s or 0, frames_dir) if info.width else None
        audio = work / f"audio{config.AUDIO_EXT}"
        info, scan = media.prepare(src, audio, lambda f: say("prepare", f, "Extracting audio and measuring"))
        frames = fut_frames.result() if fut_frames else []
    if delete_source:
        src.unlink(missing_ok=True)
    say("prepare", 1.0, f"Audio ready; {len(frames)} frames; video deleted")
    q = quality.assess(scan)
    timings["prepare_s"] = round(time.time() - t0)

    # 2. Observer, chunks in parallel
    t1 = time.time()
    chunks = observer.chunks(scan.duration_s)
    results: dict[int, merge.ChunkResult] = {}
    heard: set[str] = set()
    obs_cost, obs_stats = 0.0, []
    with ThreadPoolExecutor(PARALLEL_CHUNKS) as pool:
        futs = {pool.submit(_observe_chunk, audio, ch, frames, work): ch for ch in chunks}
        for done, fut in enumerate(as_completed(futs), 1):
            ch = futs[fut]
            try:
                r = fut.result()
                obs_cost += r.cost_usd
                obs_stats.append({"chunk": ch.i, "seconds": round(r.seconds), "cost_usd": round(r.cost_usd, 4)})
                if r.data:
                    heard.update(privacy.heard_names(r.data))
                    observer.redact(r.data, labels)
                    results[ch.i] = merge.ChunkResult(ch, r.data)
                else:
                    results[ch.i] = merge.ChunkResult(ch, None, "failed")
            except Exception:  # noqa: BLE001
                results[ch.i] = merge.ChunkResult(ch, None, "failed")
            say("observe", done / len(chunks), f"Observed {done} of {len(chunks)} chunks")
    timings["observe_s"] = round(time.time() - t1)

    # 3. merge (links speakers by heard name; the merged log has none), metrics
    merged = merge.merge(list(results.values()), scan.duration_s)
    results.clear()
    met = metrics.compute(merged, q)
    forced = metrics.forced_low_evidence(met)
    jm = metrics.judge_metrics(merged, met)
    unusable, _ = metrics.audio_minutes(merged, q)
    jin = judge.build_input(merged, met, jm, unusable, vtt_used=bool(labels))
    if privacy.leak_test_text(json.dumps(jin, ensure_ascii=False), heard, labels):
        raise PrivacyCheckFailed("A name was found in the Judge input. The report was not produced.")

    # 4. Judge scores A-E; F, the label rule and confidence are code
    t2 = time.time()
    say("judge", 0.1, "Judging")
    judged, jstats = judge.run(jin, merged.duration_s)
    if privacy.leak_test_text(json.dumps(judged, ensure_ascii=False, default=str), heard, labels):
        raise PrivacyCheckFailed("A name was found in the Judge output. The report was not produced.")
    timings["judge_s"] = round(time.time() - t2)
    f = metrics.area_f(merged, q)
    for a in forced:
        judged["areas"][a]["low_evidence"] = True
    scores = {a: judged["areas"][a]["score"] for a in judge.JUDGE_AREAS} | {"F": f["score"]}
    low_ev = sorted([a for a in judge.JUDGE_AREAS if judged["areas"][a]["low_evidence"]] + (["F"] if f["low_evidence"] else []))
    lab, M, rule = metrics.label(scores)
    conf, why = metrics.confidence(M, low_ev, met)
    say("judge", 1.0, "Judged")

    report = build_report(merged, met, jm, q, judged, f, lab, M, rule, conf, why, low_ev, info)
    report["run"] = {
        "model": gemini.MODEL, "sdk": gemini.SDK_VERSION, "observer_prompt": observer.prompt_version(),
        "judge_prompt": judge.prompt_version(), "chunks": len(chunks), "chunks_failed": merged.chunks_failed,
        "observer_cost_usd": round(obs_cost, 4), "judge_cost_usd": round(jstats["cost_usd"], 4),
        "total_cost_usd": round(obs_cost + jstats["cost_usd"], 4), "judge_checks_removed": jstats["removed"],
        "judge_input_events": len(jin["events"]),
        "timings_s": {**timings, "total_s": round(time.time() - t0)}, "observer_chunks": sorted(obs_stats, key=lambda x: x["chunk"]),
        "transcript_used_for_privacy": bool(labels),
    }
    if privacy.leak_test_text(json.dumps({k: v for k, v in report.items() if k != "quality"}, ensure_ascii=False, default=str),
                              heard, labels):
        raise PrivacyCheckFailed("A name was found in the report. The report was not shown.")
    report["run"]["leak_test"] = "passed (Judge input, Judge output, report)"
    heard.clear()
    return report


def build_report(m: merge.MergedLog, met: dict, jm: dict, q, judged: dict, f: dict, lab: str, M: float, rule: str,
                 conf: str, why: list[str], low_ev: list[str], info) -> dict:
    by_id = {e["id"]: e for e in m.events}

    def cite(c: str) -> dict:
        if c in by_id:
            e = by_id[c]
            return {"kind": "event", "id": c, "t": e["t"], "at": ts(e["t"]), "type": e["type"], "detail": e["detail"]}
        base, _, sub = c.partition(".")
        value = jm.get(base)
        if sub and isinstance(value, dict):
            value = value.get(sub)
        elif sub and isinstance(value, list):
            value = next((x for x in value if x.get("id") == sub), None)
        return {"kind": "metric", "id": c, "value": value}

    def cites(cs):
        out = [cite(c) for c in cs]
        return sorted(out, key=lambda x: (x["kind"] != "event", x.get("t", 0)))

    areas = []
    for a, w in metrics.AREAS.items():
        if a == "F":
            areas.append({"area": "F", "name": metrics.AREA_NAMES["F"], "weight": w, "score": f["score"],
                          "low_evidence": f["low_evidence"], "rationale": f"Computed in code: {f['rationale']}.",
                          "not_applicable": [], "evidence_for": [], "evidence_against": [],
                          "f_detail": {"frames_used_at": [ts(t) for t in f["frames_used"]],
                                       "frames_with_tile_hidden": f["frames_hidden"],
                                       "bad_teacher_audio_minutes": f["bad_teacher_audio_minutes"], **f["counts"]}})
            continue
        j = judged["areas"][a]
        areas.append({"area": a, "name": metrics.AREA_NAMES[a], "weight": w, "score": j["score"],
                      "low_evidence": j["low_evidence"], "rationale": j["rationale"], "not_applicable": j["not_applicable"],
                      "evidence_for": cites(j["evidence_for"]), "evidence_against": cites(j["evidence_against"])})
    return {
        "label": lab, "M": round(M, 2), "rule": rule, "confidence": conf, "confidence_reasons": why,
        "needs_human_review": conf == "Low", "summary": judged["summary"], "areas": areas, "low_evidence": low_ev,
        "strengths": [{"text": s["text"], "at": ts(s["t"]), "evidence": cites(s["evidence"])} for s in judged["strengths"]],
        "improvements": [{"text": s["text"], "at": ts(s["t"]), "evidence": cites(s["evidence"])} for s in judged["improvements"]],
        "watch": [{"at": f"{ts(w['start'])}-{ts(w['end'])}", "start": w["start"], "end": w["end"], "reason": w["reason"]}
                  for w in judged["watch"]],
        "metrics": met, "judge_metrics": jm, "quality": q,
        "recording": {"duration_min": round(m.duration_s / 60, 1),
                      "video": f"{info.width}x{info.height}" if info.width else "none"},
    }
