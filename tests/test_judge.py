"""judge.md §3 (area F) and §4 (checks on the Judge output). Synthetic data only."""
from cqa import judge, metrics
from cqa.merge import MergedLog


def frame(t, **kw):
    f = {"t": t, "teacher_tile_visible": True, "camera_on": True, "face_visible": True, "background": "8x8_branded",
         "lighting": "ok", "artefacts": False, "screen_content": "chessboard"}
    f.update(kw)
    return f


def log(frames=(), grid=(), duration=600.0):
    return MergedLog({}, [], [], list(grid), list(frames), duration, 1, 0, 0, one_to_one=False)


def test_f_hidden_tiles_are_no_data():
    frames = [frame(60 * i) for i in range(3)] + [frame(60 * i, teacher_tile_visible=False, camera_on=False,
                                                         background="unknown") for i in range(3, 9)]
    f = metrics.area_f(log(frames), None)
    assert f["score"] == 4 and not f["low_evidence"] and f["frames_hidden"] == 6


def test_f_low_evidence_under_three_visible_frames():
    assert metrics.area_f(log([frame(0), frame(60)]), None)["low_evidence"]


def test_f_rules_first_match():
    no8 = [frame(60 * i, background="real_room") for i in range(4)]
    assert metrics.area_f(log(no8), None)["score"] == 2
    one_dim = [frame(60 * i) for i in range(3)] + [frame(180, lighting="dim")]
    assert metrics.area_f(log(one_dim), None)["score"] == 3
    faceless = [frame(60 * i, face_visible=False) for i in range(3)] + [frame(180)]
    assert metrics.area_f(log(faceless), None)["score"] == 1
    bad_audio = [{"minute": m, "audio": "degraded", "affected": "teacher"} for m in range(2)]
    assert metrics.area_f(log([frame(60 * i) for i in range(4)], bad_audio, duration=600), None)["score"] == 1


JUDGE_IN = {
    "events": [{"id": "E001", "type": "greeting"}, {"id": "E002", "type": "question_directed"},
               {"id": "E003", "type": "instruction_text_seen"}],
    "metrics": {"median_wait_s": 4, "warmth_per_10min": {"humour": 0.2}, "per_child": [{"id": "S1"}]},
}


def judge_out(**area_a):
    a = {"area": "A", "evidence_for": ["E001"], "evidence_against": [], "rationale": "r", "score": 3,
         "low_evidence": False, "not_applicable": []}
    a.update(area_a)
    areas = [a] + [{**a, "area": k, "evidence_for": [], "evidence_against": []} for k in "BCDE"]
    return {"areas": areas, "summary": "s", "strengths": [], "improvements": [], "watch_minutes": []}


def test_checks_remove_bad_citations_and_apply_floor():
    d = judge_out(evidence_for=["E001", "E002", "E009", "E003", "made_up"], evidence_against=["warmth_per_10min.humour"])
    stats = {}
    out = judge.check(d, JUDGE_IN, 600, stats)
    assert out["areas"]["A"]["evidence_for"] == ["E001"]  # E002 off-area, E009 unknown, E003 never evidence
    assert out["areas"]["A"]["evidence_against"] == ["warmth_per_10min.humour"]
    assert not out["areas"]["A"]["low_evidence"]  # 2 valid citations
    assert out["areas"]["B"]["low_evidence"]  # 0 valid citations
    # instruction_text_seen is in no area's list, so it is removed as off-area too
    assert stats["removed"] == {"off_area_event": 2, "unknown_event": 1, "unknown_metric": 1}


def test_watch_windows_clamped_and_times_inside_recording():
    d = judge_out()
    d["watch_minutes"] = [{"start": "01:00", "end": "01:10", "reason": "a", "evidence": []},
                          {"start": "02:00", "end": "09:59", "reason": "b", "evidence": []},
                          {"start": "20:00", "end": "21:00", "reason": "c", "evidence": []}]
    d["strengths"] = [{"text": "ok", "t": "05:00", "evidence": []}, {"text": "late", "t": "11:00", "evidence": []}]
    out = judge.check(d, JUDGE_IN, 600, {})
    assert [(w["start"], w["end"]) for w in out["watch"]] == [(60, 120), (120, 420)]
    assert [s["text"] for s in out["strengths"]] == ["ok"]
