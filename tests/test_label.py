"""Label rule and confidence, checked against the rubric.md sanity-check table (Good >= 2.75, D13)."""
import pytest

from cqa import metrics

CASES = [  # session, A B C D E F, M, label at 2.75
    ("B491", (3, 4, 3, 2, 3, 4), 3.22, "Good"),
    ("B472", (4, 4, 3, 3, 3, 3), 3.44, "Excellent"),
    ("B552", (4, 3, 2, 3, 3, 4), 3.11, "Good"),
    ("B435-Jul", (4, 4, 3, 2, 3, 3), 3.33, "Good"),
    ("B516", (3, 4, 3, 3, 3, 2), 3.11, "Good"),
    ("B435-Aug", (3, 4, 2, 2, 3, 2), 2.78, "Good"),
    ("B558", (1, 3, 2, 1, 3, 3), 2.11, "Poor"),
    ("B482", (1, 4, 3, 3, 3, 2), 2.67, "Poor"),
]


@pytest.mark.parametrize("session,scores,m,expected", CASES)
def test_rubric_table(session, scores, m, expected):
    s = dict(zip("ABCDEF", scores))
    got, M, _ = metrics.label(s)
    assert round(M, 2) == m
    assert got == expected


def test_poor_when_mean_below_2():
    assert metrics.label(dict(zip("ABCDEF", (2, 2, 2, 1, 2, 2))))[0] == "Poor"


def test_average_when_any_area_is_1_but_not_poor():
    assert metrics.label(dict(zip("ABCDEF", (3, 4, 4, 3, 1, 4))))[0] == "Average"


def base_metrics(**kw):
    m = {"minutes_unusable_audio": 0, "minutes_total": 50, "duration_min": 50, "minutes_language_uncertain": 0,
         "chunks_failed": 0, "chunks": 5}
    m.update(kw)
    return m


def test_confidence_low_on_unusable_audio():
    assert metrics.confidence(3.0, [], base_metrics(minutes_unusable_audio=11))[0] == "Low"


def test_confidence_low_on_two_low_evidence_areas():
    assert metrics.confidence(3.0, ["B", "F"], base_metrics())[0] == "Low"


def test_confidence_medium_near_boundary():
    assert metrics.confidence(2.80, [], base_metrics())[0] == "Medium"


def test_confidence_high():
    assert metrics.confidence(3.0, [], base_metrics()) == ("High", [])
