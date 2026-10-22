"""Metrics computed in code on the merged log (observer merge rule 7, rubric areas A-F), plus the label
rule and confidence from rubric.md. The model never applies the label rule.
"""
from __future__ import annotations

from collections import Counter
from statistics import median

from .merge import MergedLog
from .quality import QualityReport

AREAS = {"A": 2, "B": 2, "C": 2, "D": 1, "E": 1, "F": 1}  # rubric weights, total 9
AREA_NAMES = {"A": "Opening and rapport", "B": "Individual attention", "C": "Warmth and energy",
              "D": "Structure, closure and homework", "E": "Active learning", "F": "Setup and presence"}
QUESTIONS = {"question_directed", "question_whole_class"}
CONTENT = {"explanation", "teacher_demo", "puzzle_start", "previous_class_link"}
WAIT_CAP_S = 60
QUIET_STRETCH_S = 300  # rubric C: 5+ minutes with no student-directed talk
F_DEGRADED_MIN = 5  # judge.md §3 / rubric F thresholds (guesses, frozen after E5)
F_DEGRADED_SHARE = 0.20
WARMTH = ("encouragement", "celebration", "humour", "patience_after_error", "impatience")


def _in_media(t: float, media: list[tuple[float, float]]) -> bool:
    return any(a <= t <= b for a, b in media)


def _minutes(spans) -> set[int]:
    return {k for s, e in spans for k in range(int(s // 60), int(max(s, e - 1) // 60) + 1)}


def audio_minutes(m: MergedLog, q: QualityReport | None) -> tuple[set[int], set[int]]:
    """(unusable minutes, degraded-or-unusable teacher-audio minutes): Observer grid plus the objective check (D18).

    The Observer rated B441's no-audio minutes "clear", so absent audio (ffmpeg) always counts as unusable and
    dense clipping as degraded. Silent gaps do not: they may be dead air or thinking time.
    """
    unusable = {g["minute"] for g in m.grid if g["audio"] == "unusable"}
    teacher_bad = {g["minute"] for g in m.grid if g["audio"] in ("degraded", "unusable") and g["affected"] in ("teacher", "all")}
    if q is not None:
        unusable |= _minutes(q.absent_spans)
        teacher_bad |= _minutes(q.absent_spans) | _minutes(q.dense_clip_spans)
    return unusable, teacher_bad


def compute(m: MergedLog, q: QualityReport | None = None) -> dict:
    ev = m.events
    minutes = max(m.duration_s / 60, 1)
    per10 = 10 / minutes
    roles = {k: v["role"] for k, v in m.people.items()}
    children = [k for k, r in roles.items() if r == "child"]
    child_turns = [t for t in m.turns if roles.get(t["speaker"]) == "child"]
    turns_by = Counter(t["speaker"] for t in child_turns)
    media = [(e["t"], e["t_end"] or e["t"]) for e in ev if e["type"] == "media_playing"]

    # --- B: individual attention
    addressed = {e["target"] for e in ev if e["type"] in ("question_directed", "check_in") and e["target"] in children}
    directed = sum(e["type"] == "question_directed" for e in ev)
    whole = sum(e["type"] == "question_whole_class" for e in ev)
    unlinked_turns = sum(not m.people.get(t["speaker"], {}).get("linked", True) for t in child_turns)
    unlinked_share = unlinked_turns / len(child_turns) if child_turns else 0.0

    # --- E: questioning and wait time
    qs = [e for e in ev if e["type"] in QUESTIONS]
    open_q = sum(e["subtype"] == "open" for e in qs)
    tturns = [t["t"] for t in child_turns]
    waits = []
    for e in qs:
        nxt = next((t for t in tturns if t > e["t"]), None)
        if nxt is not None:
            waits.append(min(nxt - e["t"], WAIT_CAP_S))
    answered_self = sum(e["type"] == "teacher_answers_own_question" for e in ev)

    # --- C / pacing: longest stretch without a child turn, media excluded
    marks = [0.0] + [t for t in tturns if not _in_media(t, media)] + [m.duration_s]
    gaps = sorted(((b - a, a) for a, b in zip(marks, marks[1:])), reverse=True)
    longest_gap, longest_at = gaps[0] if gaps else (0.0, 0.0)
    quiet_stretches = [(a, g) for g, a in gaps if g >= QUIET_STRETCH_S]

    # --- A: opening
    first_content = next((e["t"] for e in ev if e["type"] in CONTENT), None)
    greet = next((e["t"] for e in ev if e["type"] == "greeting"), None)

    unusable, degraded = audio_minutes(m, q)
    n_min = max(1, int(-(-m.duration_s // 60)))
    lang_unc = sum(g["language_uncertain"] for g in m.grid)

    # --- F: frames with the teacher tile visible only (D17)
    seen = [f for f in m.frames if f["teacher_tile_visible"]]
    def share(pred):
        return round(sum(pred(f) for f in seen) / len(seen), 2) if seen else None

    types = Counter(e["type"] for e in ev)
    return {
        "duration_min": round(minutes, 1),
        "chunks": m.chunks_total, "chunks_failed": m.chunks_failed, "rejected_items": m.rejected,
        "class_type": "1:1" if m.one_to_one else "group",
        "children": len(children),
        "children_linked": sum(m.people[c]["linked"] for c in children),
        "adults_other": sum(r == "adult" for r in roles.values()),
        "child_turns": len(child_turns),
        "child_turns_per_10min": round(len(child_turns) * per10, 1),
        "turns_per_child": dict(turns_by.most_common()),
        "top_child_turn_share": round(turns_by.most_common(1)[0][1] / len(child_turns), 2) if child_turns else None,
        "turn_subtypes": dict(Counter(t["subtype"] for t in child_turns)),
        "unlinked_child_turn_share": round(unlinked_share, 2),
        "children_addressed_share": round(len(addressed) / len(children), 2) if children else None,
        "directed_questions_per_10min": round(directed * per10, 1),
        "whole_class_questions_per_10min": round(whole * per10, 1),
        "open_question_ratio": round(open_q / len(qs), 2) if qs else None,
        "median_wait_s": round(median(waits), 1) if waits else None,
        "teacher_answers_own_question": answered_self,
        "parent_prompts": types["parent_prompt"], "redirects_to_student": types["redirect_to_student"],
        "longest_stretch_without_child_turn_s": round(longest_gap), "longest_stretch_at_s": round(longest_at),
        "quiet_stretches_5min_plus": len(quiet_stretches),
        "first_content_at_s": None if first_content is None else round(first_content),
        "greeting_at_s": None if greet is None else round(greet),
        "check_ins": types["check_in"], "topic_stated": types["topic_stated"] > 0,
        "new_joiner_present": types["new_joiner_present"] > 0,
        "new_joiner_intro_invited": types["new_joiner_intro_invited"] > 0,
        "recap": types["recap"] > 0, "homework_assigned": types["homework_assigned"] > 0, "goodbye": types["goodbye"] > 0,
        "feedback_specific": types["feedback_specific"], "feedback_generic": types["feedback_generic"],
        "encouragement": types["encouragement"], "celebration": types["celebration"], "humour": types["humour"],
        "patience_after_error": types["patience_after_error"], "impatience": types["impatience"],
        "response_to_student_comment": types["response_to_student_comment"],
        "student_moves": types["student_move"], "puzzles_started": types["puzzle_start"],
        "puzzles_solved_by_student": types["puzzle_solved_by_student"],
        "media_playing_min": round(sum(b - a for a, b in media) / 60, 1),
        "teacher_parent_exchanges": types["teacher_parent_exchange"],
        "technical_issues": types["technical_issue"], "dead_air": types["dead_air"],
        "languages": dict(Counter(e["lang"] for e in ev)),
        "minutes_total": n_min,
        "minutes_unusable_audio": len(unusable), "minutes_degraded_teacher_audio": len(degraded),
        "minutes_language_uncertain": lang_unc,
        "frames_total": len(m.frames), "frames_teacher_visible": len(seen),
        "frames_8x8_background": share(lambda f: f["background"] == "8x8_branded"),
        "frames_camera_on": share(lambda f: f["camera_on"]),
        "frames_face_visible": share(lambda f: f["face_visible"]),
        "frames_dim": share(lambda f: f["lighting"] == "dim"),
    }


# ---------------------------------------------------------------- label rule (rubric.md, applied in code)
def weighted_mean(scores: dict[str, int]) -> float:
    return sum(scores[a] * w for a, w in AREAS.items()) / sum(AREAS.values())


def label(scores: dict[str, int]) -> tuple[str, float, str]:
    """Returns (label, M, the rule line that fired)."""
    M = weighted_mean(scores)
    others = [scores[a] for a in AREAS if a != "A"]
    if M < 2.0 or (scores["A"] == 1 and min(others) <= 2):
        return "Poor", M, "M < 2.0, or A = 1 and another area <= 2"
    if M >= 3.25 and min(scores.values()) >= 3:
        return "Excellent", M, "M >= 3.25 and every area >= 3"
    if M >= 2.75 and min(scores.values()) > 1:
        return "Good", M, "M >= 2.75 and no area = 1"
    return "Average", M, "everything else"


BOUNDARIES = (2.0, 2.75, 3.25)


def confidence(M: float, low_evidence: list[str], met: dict) -> tuple[str, list[str]]:
    """rubric.md 'Confidence'. Returns (High|Medium|Low, reasons)."""
    reasons_low = []
    if met["minutes_unusable_audio"] > 0.20 * met["minutes_total"]:
        reasons_low.append(f"{met['minutes_unusable_audio']} of {met['minutes_total']} minutes have unusable audio")
    if met["duration_min"] < 20:
        reasons_low.append(f"recording is only {met['duration_min']:.0f} minutes")
    if met["minutes_language_uncertain"] > 0.30 * met["minutes_total"]:
        reasons_low.append(f"{met['minutes_language_uncertain']} minutes are in a language the Observer could not follow")
    if len(low_evidence) >= 2:
        reasons_low.append(f"little evidence for areas {', '.join(low_evidence)}")
    if met["chunks_failed"] > 0.20 * met["chunks"]:
        reasons_low.append(f"{met['chunks_failed']} of {met['chunks']} chunks failed")
    if reasons_low:
        return "Low", reasons_low
    reasons_med = []
    near = min(BOUNDARIES, key=lambda b: abs(M - b))
    if abs(M - near) <= 0.15:
        reasons_med.append(f"M = {M:.2f} is within 0.15 of the {near} boundary")
    if len(low_evidence) == 1:
        reasons_med.append(f"little evidence for area {low_evidence[0]}")
    if met["chunks_failed"]:
        reasons_med.append(f"{met['chunks_failed']} chunk(s) failed")
    return ("Medium", reasons_med) if reasons_med else ("High", [])


def forced_low_evidence(met: dict) -> list[str]:
    """Areas code marks low_evidence regardless of the Judge (D15). F is handled by area_f."""
    if met["class_type"] == "group" and met["unlinked_child_turn_share"] > 1 / 3:
        return ["B"]
    return []


def judge_metrics(m: MergedLog, met: dict) -> dict:
    """The metrics block of the Judge input (judge.md §2). Every number is computed here; the Judge never counts."""
    minutes = max(m.duration_s / 60, 1)
    per10 = 10 / minutes
    roles = {k: v["role"] for k, v in m.people.items()}
    directed = Counter(e["target"] for e in m.events if e["type"] == "question_directed")
    turns = Counter(t["speaker"] for t in m.turns if roles.get(t["speaker"]) == "child")
    children = sorted((k for k, r in roles.items() if r == "child"), key=lambda k: (-turns[k], k))
    dead = sum(((e["t_end"] or e["t"]) - e["t"]) for e in m.events if e["type"] == "dead_air")
    types = Counter(e["type"] for e in m.events)
    return {
        "minutes_to_first_content": None if met["first_content_at_s"] is None else round(met["first_content_at_s"] / 60, 1),
        "per_child": [{"id": c, "turns": turns[c], "turns_per_10min": round(turns[c] * per10, 1),
                       "directed_questions_received": directed[c]} for c in children],
        "children_addressed_share": met["children_addressed_share"],
        "directed_questions_per_10min": met["directed_questions_per_10min"],
        "whole_class_questions_per_10min": met["whole_class_questions_per_10min"],
        "open_question_ratio": met["open_question_ratio"],
        "median_wait_s": met["median_wait_s"],
        "teacher_answers_own_question": met["teacher_answers_own_question"],
        "longest_teacher_monologue_min": round(met["longest_stretch_without_child_turn_s"] / 60, 1),
        "media_minutes": met["media_playing_min"],
        "parent_prompts": met["parent_prompts"],
        "redirects_to_student": met["redirects_to_student"],
        "dead_air_minutes": round(dead / 60, 1),
        "warmth_per_10min": {k: round(types[k] * per10, 1) for k in WARMTH},
    }


def area_f(m: MergedLog, q: QualityReport | None) -> dict:
    """judge.md §3: area F from frames with the teacher tile visible and the teacher-audio minutes. First match wins."""
    vis = [f for f in m.frames if f["teacher_tile_visible"]]
    n = len(vis)
    _, bad = audio_minutes(m, q)
    total = max(1, int(-(-m.duration_s // 60)))
    off_or_no_face = sum(not f["camera_on"] or not f["face_visible"] for f in vis)
    no_face = sum(not f["face_visible"] for f in vis)
    bg8 = sum(f["background"] == "8x8_branded" for f in vis)
    dim = sum(f["lighting"] == "dim" for f in vis)
    art = sum(f["artefacts"] for f in vis)
    cam_off = sum(not f["camera_on"] for f in vis)
    frac = (lambda x: x / n) if n else (lambda x: 0.0)
    of = f"of {n} visible-tile frames"
    rules = [  # (score, condition, reason) in table order; the first score with any true condition wins
        (1, n and frac(off_or_no_face) > 0.5, f"camera off or face not visible in {off_or_no_face} {of}"),
        (1, len(bad) >= F_DEGRADED_SHARE * total, f"teacher audio degraded or missing in {len(bad)} of {total} minutes"),
        (2, n and frac(bg8) < 0.5, f"8x8 background in only {bg8} {of}"),
        (2, n and frac(no_face) > 0.2, f"face not visible in {no_face} {of}"),
        (2, n and frac(dim) > 0.5, f"dim lighting in {dim} {of}"),
        (2, n and frac(art) > 0.5, f"background artefacts in {art} {of}"),
        (2, len(bad) >= F_DEGRADED_MIN, f"{len(bad)} minutes of degraded or missing teacher audio"),
        (3, cam_off > 0, f"camera off in {cam_off} {of}"),
        (3, dim > 0, f"dim lighting in {dim} {of}"),
        (3, art > 0, f"background artefacts in {art} {of}"),
        (3, 1 <= len(bad) <= 4, f"{len(bad)} minutes of degraded or missing teacher audio"),
    ]
    score = next((sc for sc, cond, _ in rules if cond), 4)
    reasons = [why for sc, cond, why in rules if cond and sc == score]
    why = "; ".join(reasons) if reasons else "8x8 background, camera on, face visible and lit; teacher audio clear"
    return {
        "score": score, "low_evidence": n < 3, "rationale": why,
        "frames_used": [round(f["t"]) for f in vis], "frames_hidden": len(m.frames) - n,
        "bad_teacher_audio_minutes": sorted(bad),
        "counts": {"visible_frames": n, "8x8_background": bg8, "camera_off": cam_off, "face_not_visible": no_face,
                   "dim": dim, "artefacts": art},
    }
