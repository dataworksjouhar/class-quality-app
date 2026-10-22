"""Dev only: pick a local labelled recording by batch code (enabled by CQA_DEV_RECORDINGS_DIR; off in deployment).

The recording is copied into the job folder, so the pipeline deletes the copy, never the original.
File names are never shown: they can contain teacher names.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import media, vtt


def enabled() -> bool:
    return bool(os.environ.get("CQA_DEV_RECORDINGS_DIR"))


def report_dir() -> Path:
    d = Path(__file__).resolve().parent.parent / "data" / "reports"  # gitignored
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch(code: str, job_dir: Path) -> tuple[Path, str | None]:
    """Copy the recording whose file name contains `code` into job_dir; return it and its paired VTT text."""
    root = Path(os.environ["CQA_DEV_RECORDINGS_DIR"])
    code = code.strip().lower()
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        hits = [v for v in sorted(folder.glob("*.mp4")) if code and code in v.name.lower()]
        if not hits:
            continue
        src = hits[0]
        dur = media.probe(src).duration_s or 0
        # transcripts are named differently; pair by the last cue ending closest to the video's duration
        best = min(((abs((c[-1].end if (c := vtt.parse(p)) else 1e9) - dur), p) for p in folder.glob("*.vtt")),
                   default=None, key=lambda x: x[0])
        out = job_dir / "source.media"
        shutil.copyfile(src, out)
        text = best[1].read_text(encoding="utf-8", errors="replace") if best and best[0] < 600 else None
        return out, text
    raise FileNotFoundError(f"No local recording matches {code!r}.")
