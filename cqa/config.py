"""Limits and thresholds in one place, so DECISIONS.md can point at them."""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Job folders live in the system temp dir: writable on any host, never inside the repo.
DATA_DIR = Path(os.environ.get("CQA_DATA_DIR", Path(tempfile.gettempdir()) / "cqa_jobs"))

MAX_DOWNLOAD_BYTES = 1024**3  # refuse Drive files over 1 GB
DOWNLOAD_TIMEOUT_S = 30 * 60

# Audio sent to the Observer later: mono, 16 kHz, ~32 kbps (~15 MB per hour).
AUDIO_RATE = 16000
AUDIO_BITRATE = "32k"
AUDIO_EXT = ".m4a"

# Recording-quality thresholds. Calibrated once on the 12 labelled recordings (E5, D12).
QUIET_LUFS = -30.0  # integrated loudness below this = "too quiet"
LOUD_LUFS = -10.0
CLIP_LEVEL = 0.999  # |sample| at or above this counts as clipped
CLIP_SECOND_MIN = 10  # clipped samples in one second to mark that second
CLIP_DENSE_MINUTE = 10  # clipped seconds within one minute that make clipping an issue
SILENCE_DB_BELOW_SPEECH = 35.0  # a second this far under the speech level is "silent"
SILENCE_MIN_S = 20  # silent stretch this long counts as a gap
GAPS_PER_HOUR_ISSUE = 15  # this many gaps per hour = audio keeps cutting out
GAPS_MIN_COUNT = 5  # ...but never from fewer gaps than this (short files)
ABSENT_DB = -70.0  # a second below this (dBFS) has no audio at all
ABSENT_MIN_S = 60  # absent stretch this long is reported
ABSENT_ISSUE_MIN = 5.0  # minutes of absent audio (not counting the lead-in from 0:00) that raise an issue
