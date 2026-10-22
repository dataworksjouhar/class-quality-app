"""Observer pass (prompts/observer.md): chunking, inputs, one call per chunk, redaction, validation.

Merging across chunks (merge rules 3-5) is not here yet; E2 runs single chunks.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config, gemini, privacy
from .media import ffmpeg_exe

PROMPT_PATH = config.ROOT / "prompts" / "observer.md"
SCHEMA_PATH = config.ROOT / "schemas" / "observer.schema.json"
CORE_S = 600
OVERLAP_S = 30
FRAME_EVERY_S = 60
FRAME_WIDTH = 768


def prompt_version() -> str:
    first = PROMPT_PATH.read_text(encoding="utf-8").splitlines()[0]
    return re.search(r"v(\d+\.\d+)", first).group(1)


def system_prompt() -> str:
    md = PROMPT_PATH.read_text(encoding="utf-8")
    section = md[md.index("## 1. System prompt"):]
    return re.search(r"```text\n(.*?)\n```", section, re.S).group(1)


def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 60:02d}:{s % 60:02d}"


def parse_mmss(v: str) -> float | None:
    m = re.fullmatch(r"\s*(?:(\d+):)?(\d+):(\d{2}(?:\.\d+)?)\s*", v or "")
    if not m:
        return None
    return int(m[1] or 0) * 3600 + int(m[2]) * 60 + float(m[3])


@dataclass
class Chunk:
    i: int  # 1-based
    n: int
    core: tuple[float, float]  # absolute seconds
    clip: tuple[float, float]  # absolute seconds, core +/- overlap, clipped to the recording

    @property
    def clip_len(self) -> float:
        return self.clip[1] - self.clip[0]


def chunks(duration_s: float) -> list[Chunk]:
    n = max(1, -(-int(duration_s) // CORE_S))
    out = []
    for k in range(n):
        core = (k * CORE_S, min((k + 1) * CORE_S, duration_s))
        clip = (max(0.0, core[0] - OVERLAP_S), min(duration_s, core[1] + OVERLAP_S))
        out.append(Chunk(k + 1, n, core, clip))
    return out


def cut_audio(src: Path, ch: Chunk, out: Path) -> Path:
    """Observer audio for one clip, same settings as media.prepare (mono 16 kHz AAC 32k)."""
    subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{ch.clip[0]:.3f}", "-t", f"{ch.clip_len:.3f}",
         "-i", str(src), "-vn", "-ac", "1", "-ar", str(config.AUDIO_RATE), "-c:a", "aac", "-b:a", config.AUDIO_BITRATE, str(out)],
        check=True,
    )
    return out


def frame_times(ch: Chunk) -> list[float]:
    """Absolute times of frames inside the clip, on whole minutes of the class."""
    first = -(-int(ch.clip[0]) // FRAME_EVERY_S) * FRAME_EVERY_S
    return [float(t) for t in range(first, int(ch.clip[1]), FRAME_EVERY_S)]


def grab_frames(src: Path, ch: Chunk, out_dir: Path) -> list[tuple[float, Path]]:
    frames = []
    for t in frame_times(ch):
        p = out_dir / f"f{int(t):05d}.jpg"
        subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src),
             "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "5", str(p)],
            check=True,
        )
        if p.exists():
            frames.append((t, p))
    return frames


def chunk_message(ch: Chunk, with_frames: bool) -> str:
    lines = [f"Chunk {ch.i} of {ch.n}. This clip starts at {mmss(ch.clip[0])} of the class and lasts {mmss(ch.clip_len)}."]
    if ch.i == 1:
        lines.append("This clip contains the START of the class. Watch for the opening.")
    if ch.i == ch.n:
        lines.append("This clip contains the END of the class. Watch for the recap, homework and goodbye.")
    if with_frames:
        lines.append("The audio is attached. Frames follow, each preceded by its clip time.")
    else:
        lines.append("The audio is attached. No frames are attached for this clip: return an empty frames list.")
    return "\n".join(lines)


def build_parts(audio_path: Path, ch: Chunk, frames: list[tuple[float, Path]] | None) -> list[dict]:
    parts = [gemini.text(chunk_message(ch, bool(frames))), gemini.audio(audio_path)]
    for t, p in frames or []:
        parts.append(gemini.text(f"Frame at {mmss(t - ch.clip[0])}"))
        parts.append(gemini.image(p))
    return parts


def observe(audio_path: Path, ch: Chunk, frames: list[tuple[float, Path]] | None,
            thinking_level: str = "medium") -> gemini.Result:
    return gemini.interact(system_prompt(), build_parts(audio_path, ch, frames), schema(), thinking_level=thinking_level)


def redact(log: dict, vtt_labels=()) -> dict:
    """Merge rule 4 (D16): replace heard names and VTT labels in every text field. Returns counts only."""
    return dict(privacy.redact(log, vtt_labels))


def validate(log: dict, ch: Chunk) -> dict:
    """Merge rule 6 checks. Returns counts; never content."""
    ids = {r["id"] for r in log.get("roster", [])}
    bad_time = out_of_clip = bad_ref = 0
    for e in log.get("events", []):
        t = parse_mmss(e.get("t", ""))
        if t is None:
            bad_time += 1
        elif not 0 <= t <= ch.clip_len + 1:
            out_of_clip += 1
        for k in ("speaker", "target"):
            if e.get(k) and e[k] not in ids:
                bad_ref += 1
    bad_turn = 0
    for tr in log.get("student_turns", []):
        t = parse_mmss(tr.get("t", ""))
        if t is None or not 0 <= t <= ch.clip_len + 1 or tr.get("speaker") not in ids or tr.get("speaker") in ("T", "T2"):
            bad_turn += 1
    grid_minutes = sorted(g["minute"] for g in log.get("minute_grid", []))
    want = list(range(-(-int(ch.clip_len) // 60)))
    return {
        "events": len(log.get("events", [])),
        "bad_time": bad_time,
        "out_of_clip": out_of_clip,
        "unknown_speaker_or_target": bad_ref,
        "student_turns": len(log.get("student_turns", [])),
        "bad_turns": bad_turn,
        "grid_rows": len(grid_minutes),
        "grid_expected": len(want),
        "grid_complete": grid_minutes == want,
    }
