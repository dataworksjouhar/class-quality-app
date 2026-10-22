# Class Quality Assessor

Takes a recording of an online children's class and returns a label (Poor / Average / Good / Excellent),
timestamped evidence, and the minutes a QA reviewer should watch first.

**Status: skeleton.** Intake, audio extraction and the recording-quality panel work. The AI passes
(Observer, Judge) are not built yet. See `CLAUDE.md` for the plan and `DECISIONS.md` for every change to it.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin/python elsewhere
.venv/Scripts/python -m streamlit run app.py
```

ffmpeg: a system ffmpeg is used if it is on PATH; otherwise the binary from `imageio-ffmpeg` is used.

Exploration scripts (print counts and numbers only, never names or transcript text):

```bash
python scripts/inventory.py        # duration, size, format, VTT cue/speaker counts per recording
python scripts/quality_check.py    # recording-quality metrics per recording (E5)
```

Both read `RECORDINGS_DIR` from `.env`. Recordings stay outside the repo.

## Pipeline (so far)

1. **Intake.** Google Drive link (main path) or upload (≤ 200 MB). Drive files are checked first
   (restricted, missing, over 1 GB) and then streamed to disk with gdown.
2. **Prepare.** One ffmpeg pass writes mono 16 kHz AAC at 32 kbps (~13 MB per hour), measures EBU R128
   loudness, and streams PCM to numpy for the quality checks. The video is deleted straight after.
3. **Recording quality (no AI).** Loudness (EBU R128), clipping, and gaps (audio cutting out, or no audio at all), with timestamps.
   Reported separately from teaching quality.

## Data handling

- No recordings, transcripts or outputs in the repo (`.gitignore` covers media, VTT, `data/`, `.env`).
- Each run works in its own temp folder, which is deleted when the run ends.
- gdown runs with `--no-cookies`, so downloads never use anyone's Google account.

## Recording-quality check: what it catches (E5, 12 recordings)

Flags "quality issue-2" (silent gaps: 20 per hour; every other file is at 15 or fewer) and "good-1" (about 10 minutes
with no audio mid-class). It misses "quality issue-1", whose reported quietness does not show in any loudness
measure, and it does not detect the voice cracking in quality issue-2 (that is not clipping). Details in DECISIONS.md D12.
