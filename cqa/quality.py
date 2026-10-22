"""Recording-quality check: no AI, only the measurements from media.prepare.

Reported separately from teaching quality. The spans also tell the Judge where the
audio may be unreliable, so a quiet recording is not mistaken for a quiet class.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config
from .media import AudioScan

EPS = 1e-12


def ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of consecutive True values."""
    if not mask.size:
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def merge(spans: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for s, e in sorted(spans):
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


@dataclass
class Finding:
    check: str  # loudness | clipping | gaps
    is_issue: bool
    message: str
    spans: list[tuple[float, float]] = field(default_factory=list)  # seconds


@dataclass
class QualityReport:
    findings: list[Finding]
    metrics: dict
    minute_db: np.ndarray  # mean level per minute, dBFS
    minute_clipped: np.ndarray  # clipped seconds per minute
    unreliable_spans: list[tuple[float, float]]  # where the Observer/Judge should not trust the audio
    absent_spans: list[tuple[float, float]] = field(default_factory=list)  # no audio at all (after the lead-in)
    dense_clip_spans: list[tuple[float, float]] = field(default_factory=list)  # minutes with dense clipping

    @property
    def ok(self) -> bool:
        return not any(f.is_issue for f in self.findings)


def assess(scan: AudioScan) -> QualityReport:
    fps = int(round(1 / scan.frame_s))
    n_sec = len(scan.frame_ms) // fps
    sec_ms = scan.frame_ms[: n_sec * fps].reshape(n_sec, fps).mean(axis=1)
    sec_db = 10 * np.log10(sec_ms + EPS)
    n_min = max(1, -(-n_sec // 60))
    pad = n_min * 60 - n_sec
    hours = max(n_sec / 3600, 1 / 60)
    findings: list[Finding] = []

    # ---- level reference: typical level of the louder (speech) seconds
    audible = sec_db[sec_db > config.ABSENT_DB]
    speech_db = float(np.percentile(audible, 75)) if audible.size else -120.0

    # ---- loudness
    lufs = scan.lufs
    if lufs is None or not audible.size:
        findings.append(Finding("loudness", True, "No usable audio level was measured. The recording may be silent."))
    elif lufs < config.QUIET_LUFS:
        findings.append(Finding("loudness", True,
            f"Very quiet recording: {lufs:.1f} LUFS (spoken audio is usually about -16 to -23). "
            "Quiet speech may be missed; do not read low talk as a quiet class."))
    elif lufs > config.LOUD_LUFS:
        findings.append(Finding("loudness", True, f"Very loud recording: {lufs:.1f} LUFS. Expect distortion."))
    else:
        findings.append(Finding("loudness", False, f"Loudness normal: {lufs:.1f} LUFS."))

    # ---- clipping: short bursts are common (laughs, shouts); dense clipping garbles speech
    clip_mask = scan.sec_clipped[:n_sec] >= config.CLIP_SECOND_MIN
    clip_secs = int(clip_mask.sum())
    minute_clip = np.pad(clip_mask, (0, pad)).reshape(n_min, 60).sum(axis=1)
    clip_spans = merge([(float(s), float(e)) for s, e in runs(clip_mask)], gap=5)
    worst = sorted(sorted(clip_spans, key=lambda sp: -int(scan.sec_clipped[int(sp[0]):int(sp[1])].sum()))[:5])
    dense = int(minute_clip.max()) >= config.CLIP_DENSE_MINUTE
    if dense:
        msg = (f"Distorted audio: up to {int(minute_clip.max())} clipped seconds in one minute "
               f"({clip_secs} s in total). Speech there may be garbled.")
    elif clip_secs:
        msg = f"Short clipping bursts only ({clip_secs} s in total), e.g. loud laughs or shouts."
    else:
        msg = "No clipping."
    findings.append(Finding("clipping", dense, msg, worst))

    # ---- gaps: silent stretches (audio cutting out, or dead air) and stretches with no audio at all
    gaps = [(float(s), float(e)) for s, e in runs(sec_db < speech_db - config.SILENCE_DB_BELOW_SPEECH)
            if e - s >= config.SILENCE_MIN_S]
    absent = [(float(s), float(e)) for s, e in runs(sec_db < config.ABSENT_DB) if e - s >= config.ABSENT_MIN_S]
    # absent audio from 0:00 is the waiting room before class, however long; it is reported, not counted
    absent_late = [(s, e) for s, e in absent if s > 0]
    absent_min = sum(e - s for s, e in absent_late) / 60
    per_hour = len(gaps) / hours
    cutting_out = per_hour >= config.GAPS_PER_HOUR_ISSUE and len(gaps) >= config.GAPS_MIN_COUNT
    gap_issue = cutting_out or absent_min >= config.ABSENT_ISSUE_MIN
    parts = [f"{plural(len(gaps), 'silent gap', 'silent gaps')} of {config.SILENCE_MIN_S}+ s ({per_hour:.0f} per hour)"]
    if absent_late:
        parts.append(f"{absent_min:.1f} min with no audio at all")
    msg = "; ".join(parts) + "."
    if cutting_out:
        msg += " The audio keeps cutting out; the connection was probably unstable."
    elif absent_min >= config.ABSENT_ISSUE_MIN:
        msg += " Part of the class may be missing from the recording."
    lead = next((e for s, e in absent if s == 0), None)
    if lead:
        msg += f" Audio starts at {ts(lead)}."
    longest = sorted(sorted(absent_late + gaps, key=lambda sp: sp[0] - sp[1])[:6])
    findings.append(Finding("gaps", gap_issue, msg, merge(longest, gap=0)))

    minute_db = 10 * np.log10(np.pad(sec_ms, (0, pad)).reshape(n_min, 60).mean(axis=1) + EPS)
    metrics = {
        "duration_min": round(scan.duration_s / 60, 1),
        "integrated_lufs": lufs,
        "loudness_range_lu": scan.lra,
        "true_peak_dbfs": scan.true_peak_db,
        "speech_level_dbfs": round(speech_db, 1),
        "clipped_seconds": clip_secs,
        "max_clipped_seconds_in_a_minute": int(minute_clip.max()),
        "silent_gaps": len(gaps),
        "silent_gaps_per_hour": round(per_hour, 1),
        "silent_share": round(sum(e - s for s, e in gaps) / max(n_sec, 1), 3),
        "absent_audio_min": round(absent_min, 1),
    }
    unreliable = merge(clip_spans + gaps + absent_late, gap=5)
    dense = [(m * 60.0, m * 60.0 + 60) for m in np.flatnonzero(minute_clip >= config.CLIP_DENSE_MINUTE)]
    return QualityReport(findings, metrics, minute_db, minute_clip, unreliable, absent_late, dense)


def to_dict(q: QualityReport) -> dict:
    """Plain-JSON form for the report, storage and download."""
    return {"ok": q.ok, "metrics": q.metrics,
            "findings": [{"check": f.check, "is_issue": f.is_issue, "message": f.message, "spans": f.spans} for f in q.findings],
            "minute_db": [round(float(x), 1) for x in q.minute_db]}
