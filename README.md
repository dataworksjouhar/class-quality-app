# Class Quality Assessor

Takes a recording of an online children's class and returns a label (Poor / Average / Good / Excellent),
timestamped evidence, and the minutes a QA reviewer should watch first.

**Status: complete and frozen.** Evaluated on all 12 recordings (below). A run takes 6-8 minutes and costs about $0.30-0.60.
See `CLAUDE.md` for the plan and `DECISIONS.md` for every change to it.

## Using the app

Paste a Google Drive link (shared as "Anyone with the link") or upload a small file, then press **Analyse**.
**A run takes 6-8 minutes. Keep the page open; on a phone, keep the screen on.** When it finishes, the report
has its own link (kept 24 hours) and a "Download report" button.

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
   loudness and feeds the recording-quality check. In parallel, one still per minute (768 px) is taken
   from the first keyframe of each minute, labelled with its real time.
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

## Evaluation (12 recordings, prompts frozen: Observer v0.3, Judge v0.1)

**Result on the 8 labelled recordings, against trivial baselines**

| | exact | within one level | mean levels off |
|---|---|---|---|
| This app | 2 / 8 | 7 / 8 | 0.88 |
| Always "Good" | 2 / 8 | 6 / 8 | 1.00 |
| Always "Average" | 2 / 8 | 6 / 8 | 1.00 |

The app is only slightly better than answering "Good" every time. It never gave Excellent or Poor: both Excellent
classes came out Good (M 2.78 and 3.00), and both Poor classes came out Average or Good (M 2.44 and 2.78).
The scale is compressed toward the middle.

**All 12 recordings**

| code | organiser | app | M | A | B | C | D | E | F | confidence | min | time | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B472 | Excellent | Good | 2.78 | 3 | 2 | 3 | 3 | 3 | 3 | Medium | 56 | 18:25 | $0.39 |
| B491 | Excellent | Good | 3.00 | 3 | 3 | 3 | 2 | 4 | 3 | High | 54 | 47:05 | $0.45 |
| B435-Jul | Good | Average | 2.67 | 4 | 3 | 2 | 2 | 3 | 1 | Low | 44 | 7:49 | $0.28 |
| B552 | Good | Good | 3.11 | 3 | 3 | 3 | 4 | 3 | 3 | Medium | 46 | 6:49 | $0.35 |
| B435-Aug | Average | Average | 2.78 | 3 | 3 | 3 | 3 | 3 | 1 | Medium | 38 | 6:06 | $0.27 |
| B516 | Average | Good | 2.78 | 2 | 3 | 3 | 3 | 3 | 3 | Medium | 44 | 6:28 | $0.34 |
| B482 | Poor (Weak) | Average | 2.44 | 3 | 2 | 2 | 2 | 3 | 3 | High | 59 | 15:38 | $0.38 |
| B558 | Poor (Weak) | Good | 2.78 | 3 | 3 | 3 | 2 | 3 | 2 | Medium | 46 | 5:35 | $0.30 |
| B392 | (quality issue) | Good | 2.89 | 3 | 3 | 3 | 2 | 4 | 2 | Medium | 60 | 16:19 | $0.48 |
| B441 | (quality issue) | Average | 2.67 | 3 | 3 | 3 | 2 | 3 | 1 | Medium | 89 | 17:58 | $0.57 |
| EN-demo | (demo) | Good | 3.00 | 3 | 3 | 3 | 2 | 4 | 3 | High | 44 | 9:02 | $0.40 |
| ML-demo | (demo) | Good | 3.11 | 4 | 3 | 3 | 3 | 3 | 2 | Medium | 52 | 6:36 | $0.40 |

Time is wall time per recording during the evaluation, mostly with 3 recordings running at once on one laptop;
B491 and B472 also include API calls that hung before the timeout was lowered (DECISIONS D21, D23). Run alone on the
laptop after the fixes, a 54-minute class took 7 min 20 s.

**Other checks**

- **Consistency.** B558: same label and scores in three separate runs. B552: Good, M 3.11 in the evaluation and
  again in an online test from a phone via a Drive link.
- **Language fairness (E4).** English demo Good (M 3.00), Malayalam demo Good (M 3.11). A native Malayalam speaker
  checked more than 5 timestamped evidence lines in the Malayalam report against the video: all matched.
- **Recording quality.** The flag fires on B441 (audio keeps cutting out) but not on B392 (quiet teacher voice).
- **Privacy.** No names in any of the 12 reports or in the online test (independent check against every speaker
  label in the 12 transcripts).
- **Online test.** Streamlit Community Cloud, from a phone, Drive link (B552): worked end to end in about 6-8 minutes,
  with the same label and M as in the evaluation; the report had timestamps, minutes to watch and no names.

**Tested and rejected**

- **Reweighting the rubric areas** (B weight 2 -> 1, D weight 1 -> 2), computed offline on the 12 saved results with
  no new runs: exact matches stay at 2 / 8; within one level goes from 7 / 8 to 8 / 8, because B558 moves from Good
  (M 2.78) to Average (M 2.67). Also capping area A at 2 for B558 (no new-joiner introductions, tuning note T1) gives
  M 2.44 with the new weights or 2.56 with the current ones: still Average, because the Poor rule needs A = 1.
  **Rejected:** it adds no exact matches, and it would be fitted to the same 12 recordings it is tested on.
- **No tuning round.** The plan allowed one round of prompt tuning after the full evaluation. It needs the Judge
  inputs, which were not saved for the evaluated run (DECISIONS D25), so the prompts stay frozen as evaluated.
  Candidate changes are recorded, not applied (DECISIONS, tuning notes T1-T4).

**Twelve samples prove little.** The rubric anchors were written from the organiser's feedback on these same
recordings, so even these numbers are optimistic. The hidden test recording is the only clean test.

## Limitations

- **Accuracy.** Barely above the "always Good" baseline; extremes are never used (see above). Treat the label as a
  starting point and the timestamped evidence and "watch these minutes" as the useful part.
- **Forced improvements.** The Judge always lists improvements, even for a strong class, and the app does not know
  the class type: it suggested homework for a demo class, where none is expected.
- **Opening (area A).** A greeting earns credit even when new joiners are not invited to introduce themselves, the
  organiser's actual complaint in B558 (tuning note T1).
- **Pronouns.** Evidence lines refer to children as he or she (1-17 times per report): not names, but they reveal
  gender (T2).
- **Audio problems the app cannot hear.** The Observer rated almost every minute "clear", including the quality-issue
  recordings. Only ffmpeg's no-audio check found bad minutes. The voice crackle in B441 (~1:03:00) and the quiet
  teacher voice in B392 are not detected.
- **Area F counts missing audio** as a setup problem, which the rubric reserves for confidence (T3). This dropped
  B435-Jul from Good to Average.
- **Names.** Heard names and transcript labels are redacted, and a leak test blocks any report that still contains
  one. Without an uploaded transcript, the test only knows the names the Observer heard.
- **Run time and phones.** A run takes 6-8 minutes and must stay connected: if a phone sleeps or the page reloads
  mid-run, the result is lost. The page says so; surviving a reload is not built.
- **Language.** Malayalam was checked by a native speaker on one demo. Tamil switching (B392) was not checked line
  by line.

## Data handling

- No recordings, transcripts or outputs in the repo (`.gitignore` covers media, VTT, `data/`, `.env`).
- Each run works in its own temp folder, which is deleted when the run ends.
- The finished report (JSON only: no audio, stills, logs or names) is kept in the server's temp folder for 24 hours
  under a random run ID in the page URL, so a reload brings it back. Then it is deleted.
- gdown runs with `--no-cookies`, so downloads never use anyone's Google account.
- Audio and low-resolution stills go to the Gemini API (paid tier: not used for training), inline only, with
  `store=false` on every call. Google may still keep requests for up to 55 days for abuse monitoring. The app host
  (Streamlit Community Cloud) also processes the files while a run is going.
- No student names in any output: children are S1, S2…, and names are redacted before anything is stored.

## Recording-quality check: what it catches (E5, 12 recordings)

Flags "quality issue-2" (silent gaps: 20 per hour; every other file is at 15 or fewer) and "good-1" (about 10 minutes
with no audio mid-class). It misses "quality issue-1", whose reported quietness does not show in any loudness
measure, and it does not detect the voice cracking in quality issue-2 (that is not clipping). Details in DECISIONS.md D12.
