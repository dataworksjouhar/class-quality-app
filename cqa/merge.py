"""Merge per-chunk Observer logs into one class log (prompts/observer.md, merge rules 2-5).

Input logs must already be redacted (observer.redact). Heard names are used here only to link speakers
across chunks; the merged log carries no names, and the caller drops the raw logs afterwards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import privacy
from .observer import Chunk, mmss, parse_mmss

ID_IN_TEXT = re.compile(r"\[((?:S|P|U)\d+)\]")


@dataclass
class ChunkResult:
    chunk: Chunk
    log: dict | None  # redacted Observer log, or None if the chunk failed
    status: str = "ok"  # ok | failed


@dataclass
class MergedLog:
    people: dict[str, dict]  # global id -> {role, linked, chunks}
    events: list[dict]  # E001.. with absolute seconds
    turns: list[dict]  # non-teacher turns, absolute seconds
    grid: list[dict]  # one row per absolute minute that was observed
    frames: list[dict]  # absolute seconds
    duration_s: float
    chunks_total: int
    chunks_failed: int
    rejected: int  # items with a time outside their clip
    one_to_one: bool
    stats: dict = field(default_factory=dict)


def _name_key(name: str) -> str:
    return " ".join(sorted(privacy.tokens([name], stoplist=False)))


def merge(results: list[ChunkResult], duration_s: float) -> MergedLog:
    keys: dict[tuple[str, str], str] = {}  # (role, name key) -> global id
    counters = {"S": 0, "P": 0}
    people: dict[str, dict] = {}
    events, turns, grid, frames = [], [], [], []
    rejected = failed = 0
    children_per_chunk = []

    for res in sorted(results, key=lambda r: r.chunk.i):
        ch, log = res.chunk, res.log
        if log is None:
            failed += 1
            continue
        clip0, (c0, c1) = ch.clip[0], ch.core
        local: dict[str, str] = {}
        roster = sorted(log.get("roster", []), key=lambda r: parse_mmss(r.get("first_heard", "")) or 0)
        children_per_chunk.append(sum(r["role"] == "child" for r in roster))
        for r in roster:
            rid, role = r["id"], r["role"]
            if role == "teacher":
                gid = "T2" if rid == "T2" else "T"
            elif role == "media":
                gid = "V"
            elif role in ("child", "adult") and (key := _name_key(r.get("name_heard", ""))):
                prefix = "S" if role == "child" else "P"
                if (role, key) not in keys:
                    counters[prefix] += 1
                    keys[(role, key)] = f"{prefix}{counters[prefix]}"
                gid = keys[(role, key)]
            else:
                gid = f"c{ch.i}-{rid}"  # unlinked: chunk-local
            local[rid] = gid
            p = people.setdefault(gid, {"role": role, "linked": not gid.startswith("c"), "chunks": []})
            if ch.i not in p["chunks"]:
                p["chunks"].append(ch.i)

        def gmap(x: str) -> str:
            return local.get(x, x) if x else x

        def gtext(s: str) -> str:
            return ID_IN_TEXT.sub(lambda m: f"[{local.get(m.group(1), m.group(1))}]", s or "")

        def absolute(t: str) -> float | None:
            v = parse_mmss(t)
            if v is None or not -1 <= v <= ch.clip_len + 1:
                return None
            return clip0 + v

        for e in log.get("events", []):
            t = absolute(e.get("t", ""))
            if t is None:
                rejected += 1
                continue
            if not c0 <= t < c1:
                continue  # belongs to the neighbouring chunk's core window
            t_end = absolute(e.get("t_end", "")) if e.get("t_end") else None
            events.append({**e, "t": t, "t_end": t_end, "speaker": gmap(e.get("speaker", "")),
                           "target": gmap(e.get("target", "")), "detail": gtext(e.get("detail", "")),
                           "quote_en": gtext(e.get("quote_en", "")), "chunk": ch.i})
        for tr in log.get("student_turns", []):
            t = absolute(tr.get("t", ""))
            if t is None:
                rejected += 1
            elif c0 <= t < c1:
                turns.append({"t": t, "speaker": gmap(tr["speaker"]), "subtype": tr.get("subtype", "")})
        for g in log.get("minute_grid", []):
            start = clip0 + 60 * int(g["minute"])
            # a clip minute belongs to the core window that holds most of it
            if c0 <= start + 30 < c1:
                grid.append({**g, "minute": int((start + 30) // 60), "reason": gtext(g.get("reason", ""))})
        for f in log.get("frames", []):
            t = absolute(f.get("t", ""))
            if t is not None and c0 <= t < c1:
                frames.append({**f, "t": t})

    events.sort(key=lambda e: e["t"])
    for n, e in enumerate(events, 1):
        e["id"] = f"E{n:03d}"
    turns.sort(key=lambda x: x["t"])
    grid = list({g["minute"]: g for g in sorted(grid, key=lambda g: g["minute"])}.values())
    frames.sort(key=lambda f: f["t"])
    return MergedLog(people, events, turns, grid, frames, duration_s, len(results), failed, rejected,
                     one_to_one=bool(children_per_chunk) and max(children_per_chunk) <= 1)


def to_judge_input(m: MergedLog) -> dict:
    """The merged log as the Judge sees it: IDs, times as H:MM:SS, no names (there are none to begin with)."""
    def ts(s):
        return None if s is None else mmss(s) if s < 3600 else f"{int(s // 3600)}:{mmss(s % 3600)}"

    return {
        "people": {k: {"role": v["role"], "linked": v["linked"]} for k, v in m.people.items()},
        "events": [{"id": e["id"], "t": ts(e["t"]), "t_end": ts(e["t_end"]), "type": e["type"], "subtype": e["subtype"],
                    "speaker": e["speaker"], "target": e["target"], "lang": e["lang"], "detail": e["detail"],
                    "quote_en": e["quote_en"], "confidence": e["confidence"]} for e in m.events],
        "student_turns": [f"{ts(t['t'])} {t['speaker']} {t['subtype']}" for t in m.turns],
        "minute_grid": [{"minute": g["minute"], "audio": g["audio"], "affected": g["affected"], "phase": g["phase"],
                         "language": g["language"], "language_uncertain": g["language_uncertain"]} for g in m.grid],
        "frames": [{k: v for k, v in f.items() if k != "t"} | {"t": ts(f["t"])} for f in m.frames],
    }
