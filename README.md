# Class Quality Assessor

Takes a recording of an online children's class and returns a label (Poor / Average / Good / Excellent),
timestamped evidence, and the minutes a QA reviewer should watch first.

**Status: full pipeline works end to end.** Tested on one labelled class so far (B558, 46 min: 4-5 min, about $0.30).
See `CLAUDE.md` for the plan and `DECISIONS.md` for every change to it.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin/python elsewhere
.venv/Scripts/python -m streamlit run app.py
```

ffmpeg: a system ffmpeg is used if it is on PATH; otherwise the binary from `imageio-ffmpeg` is used.

Put `GEMINI_API_KEY` in `.env` locally, or in the app's Secrets on Streamlit Community Cloud. Setting
`CQA_DEV_RECORDINGS_DIR` in `.env` adds a dev-only "Local (dev)" input that runs a local labelled recording by
batch code (it works on a copy, and saves the name-free report JSON to `data/reports/`). Leave it unset in deployment.

Exploration scripts (print counts and numbers only, never names or transcript text):

```bash
python scripts/inventory.py        # duration, size, format, VTT cue/speaker counts per recording
python scripts/quality_check.py    # recording-quality metrics per recording (E5)
python scripts/e2_observer.py run B472 --chunk 2   # one Observer chunk, saved to data/e2 (E2)
```

Both read `RECORDINGS_DIR` from `.env`. Recordings stay outside the repo.

## Pipeline

1. **Intake.** Google Drive link (main path) or upload (≤ 200 MB). Drive files are checked first
   (restricted, missing, over 1 GB) and then streamed to disk with gdown.
2. **Prepare.** One ffmpeg pass writes mono 16 kHz AAC at 32 kbps (~13 MB per hour), measures EBU R128
   loudness and feeds the recording-quality check; one still per minute (768 px) is taken in parallel.
   The video is deleted straight after.
3. **Observer** (`prompts/observer.md`, Gemini, audio + stills). 10-minute chunks with 30 s overlap, 4 in parallel.
   Each chunk returns a JSON log of timestamped events, every student turn, a minute grid and frame notes.
   Heard names and transcript labels are redacted in code before anything is stored (`cqa/privacy.py`).
4. **Merge and metrics** (code). Speakers are linked across chunks by heard name, then the names are dropped.
   Turns per child, questions, wait time, longest teacher stretch, warmth events, audio minutes, frames.
5. **Judge** (`prompts/judge.md`, text only). Scores areas A-E, citing event IDs or metric names; code checks
   every citation. Area F, the label rule and confidence are computed in code from `rubric.md`.
6. **Report.** Label, confidence, one-line summary, scores with timestamped evidence, strengths, improvements,
   minutes to watch, and the recording-quality panel. A name leak test runs on the Judge input, the Judge
   output and the report; any hit stops the run.

**Recording quality (no AI).** Loudness (EBU R128), clipping, and gaps (audio cutting out, or no audio at all),
with timestamps. Reported separately from teaching quality; absent audio also counts as unusable minutes.

Tests: `python -m pytest tests` (label rule against the rubric's sanity table, area F, Judge checks, redaction).

## Data handling

- No recordings, transcripts or outputs in the repo (`.gitignore` covers media, VTT, `data/`, `.env`).
- Each run works in its own temp folder, which is deleted when the run ends.
- gdown runs with `--no-cookies`, so downloads never use anyone's Google account.

## Recording-quality check: what it catches (E5, 12 recordings)

Flags "quality issue-2" (silent gaps: 20 per hour; every other file is at 15 or fewer) and "good-1" (about 10 minutes
with no audio mid-class). It misses "quality issue-1", whose reported quietness does not show in any loudness
measure, and it does not detect the voice cracking in quality issue-2 (that is not clipping). Details in DECISIONS.md D12.
