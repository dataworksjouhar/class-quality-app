"""Judge pass (prompts/judge.md v0.1): text only, scores areas A-E with cited event IDs or metric names.

Area F, the label rule and confidence are applied in code (metrics.py), never by the model.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from . import config, gemini
from .merge import MergedLog
from .observer import parse_mmss
from .quality import ts

PROMPT_PATH = config.ROOT / "prompts" / "judge.md"
SCHEMA_PATH = config.ROOT / "schemas" / "judge.schema.json"
JUDGE_AREAS = ("A", "B", "C", "D", "E")
EVENT_ID = re.compile(r"^E\d{3,}$")
# judge.md §4 check 2: event types each area accepts as evidence. A and B are from the spec;
# C-E follow the "Observer logs" lines of rubric.md (D18).
AREA_EVENTS = {
    "A": {"greeting", "check_in", "topic_stated", "previous_class_link", "new_joiner_present", "new_joiner_intro_invited"},
    "B": {"question_directed", "question_whole_class", "student_utterance", "parent_prompt", "redirect_to_student"},
    "C": {"encouragement", "celebration", "humour", "patience_after_error", "impatience", "response_to_student_comment",
          "feedback_generic", "feedback_specific", "dead_air"},
    "D": {"topic_stated", "previous_class_link", "recap", "homework_assigned", "goodbye", "media_playing", "explanation",
          "puzzle_start"},
    "E": {"question_directed", "question_whole_class", "student_utterance", "student_move", "puzzle_start",
          "puzzle_solved_by_student", "teacher_answers_own_question", "feedback_specific", "redirect_to_student",
          "teacher_demo", "explanation"},
}
WATCH_MIN_S, WATCH_MAX_S = 60, 300
JUDGE_TIMEOUT_S = 360  # Judge calls take 50-190 s with thinking "high"; the 240 s default was too tight (D24)


def prompt_version() -> str:
    return re.search(r"v(\d+\.\d+)", PROMPT_PATH.read_text(encoding="utf-8").splitlines()[0]).group(1)


def system_prompt() -> str:
    md = PROMPT_PATH.read_text(encoding="utf-8")
    return re.search(r"```text\n(.*?)\n```", md[md.index("## 1. System prompt"):], re.S).group(1)


def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _ranges(minutes: set[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for m in sorted(minutes):
        if out and m == out[-1][1] + 1:
            out[-1][1] = m
        else:
            out.append([m, m])
    return out


def build_input(m: MergedLog, met: dict, jm: dict, unusable_minutes: set[int], vtt_used: bool) -> dict:
    """judge.md §2: session + metrics + events (no student turns, grid or frames)."""
    langs = Counter()
    for g in m.grid:
        lang = (g.get("language") or "").lower()
        langs["mixed" if "+" in lang or "," in lang else lang or "unknown"] += 1
    return {
        "session": {"duration_min": round(m.duration_s / 60), "class_type": met["class_type"],
                    "children_present": met["children"], "vtt_used": vtt_used,
                    "unusable_audio_minutes": _ranges(unusable_minutes), "language_minutes": dict(langs)},
        "metrics": jm,
        "events": [{"id": e["id"], "t": ts(e["t"]), "t_end": ts(e["t_end"]) if e["t_end"] is not None else "",
                    "type": e["type"], "subtype": e["subtype"], "speaker": e["speaker"], "target": e["target"],
                    "detail": e["detail"], "quote_en": e["quote_en"]} for e in m.events],
    }


def _metric_names(jm: dict) -> set[str]:
    names = set(jm)
    names |= {f"warmth_per_10min.{k}" for k in jm.get("warmth_per_10min", {})}
    names |= {f"per_child.{c['id']}" for c in jm.get("per_child", [])}
    return names


def _ok(d: dict | None) -> bool:
    if not d or not isinstance(d.get("areas"), list):
        return False
    got = {a.get("area") for a in d["areas"]}
    return got == set(JUDGE_AREAS) and all(isinstance(a.get("score"), int) and 1 <= a["score"] <= 4 for a in d["areas"])


def run(judge_input: dict, duration_s: float, thinking_level: str = "high") -> tuple[dict, dict]:
    """judge.md §4 check 6: retry once on invalid JSON or a missing area, then fail."""
    parts = [gemini.text(json.dumps(judge_input, ensure_ascii=False))]
    stats = {"seconds": 0.0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "thought_tokens": 0, "attempts": 0,
             "api_errors": 0, "calls": []}
    for _ in range(2):
        r = gemini.interact(system_prompt(), parts, schema(), thinking_level=thinking_level, timeout_s=JUDGE_TIMEOUT_S)
        for k, v in (("seconds", r.seconds), ("cost_usd", r.cost_usd), ("input_tokens", r.input_tokens),
                     ("output_tokens", r.output_tokens), ("thought_tokens", r.thought_tokens), ("attempts", r.attempts),
                     ("api_errors", r.api_errors)):
            stats[k] += v
        stats["calls"] += r.calls
        if _ok(r.data):
            return check(r.data, judge_input, duration_s, stats), stats
    raise RuntimeError("The Judge did not return a valid score for every area after one retry.")


def check(d: dict, judge_input: dict, duration_s: float, stats: dict) -> dict:
    """judge.md §4 checks 1-4. Removed citations and items are counted in stats."""
    events = {e["id"]: e for e in judge_input["events"]}
    metric_names = _metric_names(judge_input["metrics"])
    removed = Counter()

    def valid(cite: str, area: str | None) -> bool:
        c = cite.strip()
        if EVENT_ID.match(c):
            if c not in events:
                removed["unknown_event"] += 1
                return False
            if area and events[c]["type"] not in AREA_EVENTS[area]:
                removed["off_area_event"] += 1
                return False
            return events[c]["type"] != "instruction_text_seen"
        if c in metric_names:
            return True
        removed["unknown_metric"] += 1
        return False

    areas = {}
    for a in d["areas"]:
        k = a["area"]
        ev_for = [c.strip() for c in a["evidence_for"] if valid(c, k)]
        ev_against = [c.strip() for c in a["evidence_against"] if valid(c, k)]
        areas[k] = {**a, "evidence_for": ev_for, "evidence_against": ev_against,
                    "low_evidence": bool(a["low_evidence"] or len(ev_for) + len(ev_against) < 2)}

    def in_recording(t: str) -> float | None:
        v = parse_mmss(t)
        return v if v is not None and 0 <= v <= duration_s else None

    lists = {}
    for key in ("strengths", "improvements"):
        keep = []
        for s in d[key]:
            t = in_recording(s["t"])
            if t is None:
                removed[f"{key}_bad_time"] += 1
                continue
            keep.append({"text": s["text"], "t": t, "evidence": [c.strip() for c in s["evidence"] if valid(c, None)]})
        lists[key] = keep
    watch = []
    for w in d["watch_minutes"]:
        s, e = in_recording(w["start"]), parse_mmss(w["end"])
        if s is None or e is None:
            removed["watch_bad_time"] += 1
            continue
        e = min(max(e, s + WATCH_MIN_S), s + WATCH_MAX_S, duration_s)
        watch.append({"start": s, "end": e, "reason": w["reason"],
                      "evidence": [c.strip() for c in w["evidence"] if valid(c, None)]})
    watch.sort(key=lambda w: w["start"])
    stats["removed"] = dict(removed)
    return {"areas": areas, "summary": d["summary"], **lists, "watch": watch}
