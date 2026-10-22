"""E2: run the Observer on one chunk of a recording and check the log. Prints counts only.

Usage:
  python scripts/e2_observer.py run   <code> [--chunk 2] [--no-frames] [--thinking medium]
  python scripts/e2_observer.py check <code> [--chunk 2]
<code> is a batch code (B472) or "ML-demo" for the Malayalam demo.
Full outputs go to data/e2/ (gitignored). Names and quotes are never printed.
"""
import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

from cqa import gemini, media, observer, privacy, vtt  # noqa: E402
from inventory import pair_transcripts  # noqa: E402

OUT = ROOT / "data" / "e2"
TEACHER_TYPES = {"greeting", "check_in", "topic_stated", "question_directed", "question_whole_class", "explanation",
                 "feedback_specific", "feedback_generic", "encouragement", "teacher_demo", "puzzle_start",
                 "patience_after_error", "response_to_student_comment", "redirect_to_student", "recap"}


def find_recording(code: str) -> tuple[Path, Path | None]:
    root = Path(os.environ["RECORDINGS_DIR"])
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        videos = sorted(folder.glob("*.mp4"))
        hit = [v for v in videos if (code.lower() == "ml-demo" and "malayalam" in v.name.lower())
               or code.lower() in v.name.lower()]
        if hit:
            pairs = pair_transcripts([(v, media.probe(v).duration_s) for v in videos], sorted(folder.glob("*.vtt")))
            return hit[0], (pairs[hit[0]][0] if hit[0] in pairs else None)
    raise SystemExit(f"No recording for {code}")


def out_path(code: str, chunk: int, frames: bool, version: str | None = None) -> Path:
    v = version or observer.prompt_version()
    suffix = "" if v == "0.1" else f"_v{v}"  # v0.1 files predate versioned names
    return OUT / f"{code}_c{chunk}_{'frames' if frames else 'noframes'}{suffix}.json"


def vtt_labels(vtt_path: Path | None) -> list[str]:
    return sorted({c.speaker for c in vtt.parse(vtt_path) if c.speaker}) if vtt_path else []


def run(args) -> None:
    src, vtt_path = find_recording(args.code)
    dur = media.probe(src).duration_s
    ch = observer.chunks(dur)[args.chunk - 1]
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audio = observer.cut_audio(src, ch, tmp / "clip.m4a")
        frames = None if args.no_frames else observer.grab_frames(src, ch, tmp)
        res = observer.observe(audio, ch, frames, thinking_level=args.thinking)
        payload_mb = sum(len(p.get("data", "")) for p in observer.build_parts(audio, ch, frames)) / 1e6
    leaks_before, redactions = {}, {}
    if res.data:
        leaks_before = dict(privacy.leak_test(res.data, privacy.heard_names(res.data), vtt_labels(vtt_path)))
        redactions = observer.redact(res.data, vtt_labels(vtt_path))
    rec = {
        "code": args.code, "prompt_version": observer.prompt_version(), "chunk": ch.i, "n_chunks": ch.n, "core": ch.core, "clip": ch.clip,
        "frames_sent": len(frames or []), "model": gemini.MODEL, "sdk": gemini.SDK_VERSION,
        "thinking_level": args.thinking, "status": res.status, "attempts": res.attempts,
        "seconds": round(res.seconds, 1), "payload_mb": round(payload_mb, 2),
        "usage": {"input": res.input_tokens, "output": res.output_tokens, "thought": res.thought_tokens,
                  "input_by_modality": res.input_by_modality},
        "cost_usd": round(res.cost_usd, 4),
        "leaks_before_redaction": leaks_before, "redactions": redactions,
        "log": res.data, "raw_text": None if res.data else "(unparsed output not saved: it may contain names)",
    }
    p = out_path(args.code, ch.i, bool(frames))
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.code} v{observer.prompt_version()} chunk {ch.i}/{ch.n} frames={len(frames or [])}: status={res.status} attempts={res.attempts} "
          f"parsed={res.data is not None} {res.seconds:.0f}s ${res.cost_usd:.4f} payload {payload_mb:.1f} MB")


# ---------------------------------------------------------------- checks
def nearest(t: float, starts: list[float]) -> float | None:
    return min((t - s for s in starts), key=abs) if starts else None


def check(args) -> None:
    src, vtt_path = find_recording(args.code)
    cues = vtt.parse(vtt_path) if vtt_path else []
    words = Counter()
    for c in cues:
        if c.speaker:
            words[c.speaker] += len(c.text.split())
    teacher_label = words.most_common(1)[0][0] if words else None
    runs = {}
    for version in ("0.1", observer.prompt_version()):
        for frames in (True, False):
            p = out_path(args.code, args.chunk, frames, version)
            if p.exists():
                runs[f"v{version} {'frames' if frames else 'noframes'}"] = json.loads(p.read_text(encoding="utf-8"))
    if not runs:
        raise SystemExit("No saved runs.")
    for kind, rec in runs.items():
        print(f"\n=== {args.code} chunk {rec['chunk']}/{rec['n_chunks']} [{kind}]  clip {observer.mmss(rec['clip'][0])}"
              f"-{observer.mmss(rec['clip'][1])}  {rec['model']}  thinking={rec['thinking_level']}")
        u = rec["usage"]
        print(f"cost ${rec['cost_usd']:.4f}  time {rec['seconds']:.0f}s  attempts {rec['attempts']}  status {rec['status']}  "
              f"tokens in {u['input']} ({u['input_by_modality']}) out {u['output']} thought {u['thought']}  "
              f"payload {rec['payload_mb']} MB")
        log = rec["log"]
        if not log:
            print("NO PARSED LOG")
            continue
        clip0, clip1 = rec["clip"]
        ch = observer.Chunk(rec["chunk"], rec["n_chunks"], tuple(rec["core"]), (clip0, clip1))
        print("validation:", observer.validate(log, ch))

        roles = {r["id"]: r["role"] for r in log["roster"]}
        print("roster:", dict(Counter(r["role"] for r in log["roster"])),
              "| with name_heard:", dict(Counter(r["role"] for r in log["roster"] if r["name_heard"].strip())))
        print("event types:", dict(Counter(e["type"] for e in log["events"]).most_common()))
        print("event langs:", dict(Counter(e["lang"] for e in log["events"])),
              "| confidence:", dict(Counter(e["confidence"] for e in log["events"])))
        g = log["minute_grid"]
        print("grid audio:", dict(Counter(x["audio"] for x in g)), "| language_uncertain:",
              sum(x["language_uncertain"] for x in g), "of", len(g), "| languages:", dict(Counter(x["language"] for x in g)),
              "| phases:", dict(Counter(x["phase"] for x in g)))
        if log["frames"]:
            f = log["frames"]
            print(f"frames returned {len(f)} (sent {rec['frames_sent']}): background {dict(Counter(x['background'] for x in f))}"
                  f" | screen {dict(Counter(x['screen_content'] for x in f))} | camera_on {sum(x['camera_on'] for x in f)}"
                  f" face {sum(x['face_visible'] for x in f)} dim {sum(x['lighting'] == 'dim' for x in f)}"
                  f" artefacts {sum(x['artefacts'] for x in f)}")
        else:
            print(f"frames returned 0 (sent {rec['frames_sent']})")

        # --- timestamps vs VTT (absolute seconds)
        in_clip = [c for c in cues if clip0 <= c.start <= clip1]
        t_starts = [c.start for c in in_clip if c.speaker == teacher_label]
        s_starts = [c.start for c in in_clip if c.speaker and c.speaker != teacher_label]
        for label, evs, starts in (
            ("teacher", [e for e in log["events"] if e["speaker"] == "T" and e["type"] in TEACHER_TYPES], t_starts),
            ("child", [e for e in log["events"] if e["type"] == "student_utterance" and roles.get(e["speaker"]) == "child"], s_starts),
        ):
            offs = [o for e in evs if (t := observer.parse_mmss(e["t"])) is not None
                    and (o := nearest(t + clip0, starts)) is not None]
            if offs:
                third = max(1, len(offs) // 3)
                print(f"align {label}: n={len(offs)} vs {len(starts)} VTT cues | median |offset| {median(map(abs, offs)):.1f}s"
                      f" signed {median(offs):+.1f}s | within 5s {sum(abs(o) <= 5 for o in offs) / len(offs):.0%}"
                      f" | signed first third {median(offs[:third]):+.1f}s last third {median(offs[-third:]):+.1f}s")
            else:
                print(f"align {label}: no events or no VTT cues ({len(evs)} events, {len(starts)} cues)")
        nonteacher_core = [c for c in cues if c.speaker and c.speaker != teacher_label and ch.core[0] <= c.start < ch.core[1]]
        other_ev = [observer.parse_mmss(e["t"]) + clip0 for e in log["events"]
                    if e["speaker"] and e["speaker"] not in ("T", "T2") and observer.parse_mmss(e["t"]) is not None]
        turns = [(observer.parse_mmss(x["t"]) + clip0, x["speaker"]) for x in log.get("student_turns", [])
                 if observer.parse_mmss(x["t"]) is not None]
        if nonteacher_core:
            cov = sum(any(abs(c.start - t) <= 10 for t in other_ev) for c in nonteacher_core) / len(nonteacher_core)
            line = (f"coverage: events {cov:.0%} of {len(nonteacher_core)} non-teacher VTT cues (core window) "
                    f"have a non-teacher event within 10 s")
            if "student_turns" in log:
                tt = [t for t, _ in turns]
                c5 = sum(any(abs(c.start - t) <= 5 for t in tt) for c in nonteacher_core) / len(nonteacher_core)
                c10 = sum(any(abs(c.start - t) <= 10 for t in tt) for c in nonteacher_core) / len(nonteacher_core)
                core_turns = [t for t in tt if ch.core[0] <= t < ch.core[1]]
                others = [c.start for c in in_clip if c.speaker and c.speaker != teacher_label]
                prec = sum(any(abs(c - t) <= 5 for c in others) for t in core_turns) / max(len(core_turns), 1)
                line += (f"\n  turns: {len(core_turns)} in core vs {len(nonteacher_core)} VTT cues | cues with a turn "
                         f"within 5 s {c5:.0%}, 10 s {c10:.0%} | turns with a non-teacher cue within 5 s {prec:.0%}")
            print(line)
            in_core = [(t, sp) for t, sp in turns if ch.core[0] <= t < ch.core[1]]
            if in_core:
                print(f"  turns by role {dict(Counter(roles.get(sp, '?') for _, sp in in_core))} | "
                      f"by speaker {dict(Counter(sp for _, sp in in_core).most_common())}")

        # --- linking: heard names vs VTT speakers in this window
        children = [r for r in log["roster"] if r["role"] == "child"]
        linked = {r["id"] for r in children if r["name_heard"].strip()}
        child_turns = [e for e in log["events"] if e["type"] == "student_utterance" and roles.get(e["speaker"]) == "child"]
        vtt_window = {c.speaker for c in cues if c.speaker and c.speaker != teacher_label and clip0 <= c.start <= clip1}
        kid_turns = [sp for _, sp in turns if roles.get(sp) == "child"]
        print(f"linking: {len(linked)} of {len(children)} children have a heard name; "
              f"{sum(e['speaker'] in linked for e in child_turns)} of {len(child_turns)} child utterance events linked; "
              f"{sum(sp in linked for sp in kid_turns)} of {len(kid_turns)} child turns linked | "
              f"VTT non-teacher speakers in clip: {len(vtt_window)} (whole recording: {len(words) - 1})")

        # --- leak test: heard names + VTT labels, outside name_heard
        names = privacy.heard_names(log) + list(words)
        after = privacy.leak_test(log, privacy.heard_names(log), list(words))
        before = rec.get("leaks_before_redaction")
        print(f"leak test: {len(privacy.tokens(names))} name tokens | before redaction "
              f"{'not recorded (v0.1 run)' if before is None else (before or 'none')} | redactions "
              f"{rec.get('redactions', 'n/a (v0.1)') or 'none'} | after {dict(after) or 'none'}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "check"])
    ap.add_argument("code")
    ap.add_argument("--chunk", type=int, default=2)
    ap.add_argument("--no-frames", action="store_true")
    ap.add_argument("--thinking", default="medium")
    args = ap.parse_args()
    (run if args.cmd == "run" else check)(args)


if __name__ == "__main__":
    main()
