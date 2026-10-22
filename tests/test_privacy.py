"""Redaction tests. All names are invented."""
from cqa import privacy


def make_log(details, name_heard="", vtt_labels=()):
    roster = [{"id": "T", "role": "teacher", "name_heard": "", "voice_note": "", "unsure_reason": ""},
              {"id": "S1", "role": "child", "name_heard": name_heard, "voice_note": "", "unsure_reason": ""}]
    return {"roster": roster, "events": [{"detail": d, "quote_en": ""} for d in details], "minute_grid": []}


def texts(log):
    return [e["detail"] for e in log["events"]]


def test_heard_name_and_spelling_variant():
    log = make_log(["Teacher asks Xaadhu", "Xadhu answers"], name_heard="Xaadhu")
    privacy.redact(log)
    assert texts(log) == ["Teacher asks [S1]", "[S1] answers"]


def test_chess_word_that_is_a_heard_name_is_redacted():
    # A child called Raja: "raja" (king) is redacted everywhere. Privacy wins over clarity.
    log = make_log(["Raja moves the knight", "Explains that the raja must escape check"], name_heard="Raja")
    privacy.redact(log)
    assert texts(log) == ["[S1] moves the knight", "Explains that the [S1] must escape check"]


def test_rani_from_vtt_label_is_redacted():
    log = make_log(["Rani says the rani is attacked", "The queen is attacked"])
    privacy.redact(log, vtt_labels=["Rani Plaxton"])
    assert texts(log) == ["[name] says the [name] is attacked", "The queen is attacked"]


def test_chess_words_untouched_when_nobody_has_that_name():
    log = make_log(["The raja and rani are on e1 and d1; the king is safe"], name_heard="Quillon")
    assert not privacy.redact(log, vtt_labels=["Vexmor's iPhone"])
    assert texts(log) == ["The raja and rani are on e1 and d1; the king is safe"]


def test_chess_words_never_fuzzy_match_a_name():
    # "rajah" is close to a name like "Rajzot" but is a chess word, so only an exact name match may redact it.
    log = make_log(["The rajah is safe"], name_heard="Rajzot")
    privacy.redact(log)
    assert texts(log) == ["The rajah is safe"]


def test_zoom_system_label_is_not_a_name():
    log = make_log(["Teacher audio clear; screen shared"])
    assert not privacy.redact(log, vtt_labels=["Shared Audio"])


def test_leak_test_finds_nothing_after_redaction():
    log = make_log(["Raja and Zorvelika solve it", "Zorveliqa again"], name_heard="Raja", vtt_labels=["Zorvelika Q"])
    assert privacy.leak_test(log, ["Raja"], ["Zorvelika Q"])
    privacy.redact(log, vtt_labels=["Zorvelika Q"])
    assert not privacy.leak_test(log, ["Raja"], ["Zorvelika Q"])


def test_substring_scan_stays_inside_words():
    # "the rook" squashed is "terok"; a label token spanning two words is a letter accident, not a name
    log = make_log(["Teacher Zemblor explains", "Students practise with the rook"])
    assert privacy.leak_test(log, [], ["Zemblor"]) == {"events.detail:exact": 1}
    glued = make_log(["Praised ZorvelikaQuen for the move"])
    assert privacy.leak_test(glued, [], ["Zorvelika Q"])


def test_name_heard_in_another_chunk_is_redacted():
    # chunk 1 mentions a child whose name only reached the roster in chunk 3 (D22)
    log = make_log(["Teacher asks Quorvanth to move"])
    assert not privacy.redact(log)  # this chunk's roster has no such name
    privacy.redact(log, other_heard=["Quorvanth"])
    assert texts(log) == ["Teacher asks [name] to move"]
