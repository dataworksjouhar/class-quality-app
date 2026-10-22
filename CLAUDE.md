# Build Brief: Class Quality Assessor (Humaniti AI challenge)

This plan was drafted in an earlier planning session. Treat it as a starting point: challenge it, test it, and change it when the evidence says so. Log every change in DECISIONS.md.

## 1. Goal

Build a simple hosted app. It takes a recording of an online children's class (8x8, mostly chess) and returns:
- a label: Poor, Average, Good or Excellent
- specific, timestamped observations that explain the label
- the minutes a human reviewer should watch first

The user of the report is a QA reviewer who has two minutes, not two hours.

## 2. Facts about the data (from a count-only inventory)

- 12 recordings in 6 folders: average, demo, excellent, good, quality issue, weak. Two in each.
- Length 38 to 89 minutes. Size 54 to 340 MB. All 1080p, AAC stereo audio. About 10.5 hours in total.
- Each recording has a Zoom VTT transcript with speaker labels.
- The Malayalam demo transcript is not usable. The class is clearly in Malayalam, but the VTT is English captioning that guessed at the speech. Confirmed by a Malayalam speaker.
- Some speaker labels appear under more than one quality level. The app must grade the session, not the teacher.
- No single metric separates the levels. The main speaker's share of words is 50 to 80 percent in every folder.
- The test recording may arrive without a transcript.
- The classes are online chess lessons from 8x8 (Eight Times Eight, an Indian chess academy). They are taught over Zoom, often with a lichess.org board shared on screen. The academy promises "personalized attention".
- From human review of the "quality issue" folder: the problems are technical and about delivery, not teaching. In one recording the audio is much quieter than the others. In the other, the voice is distorted and cracks (for example around 1:03:00). In one recording the teacher also switches to Tamil at times, with some students or parents.
- So the classes use at least three languages: English, Malayalam and Tamil, sometimes mixed in one sentence.

## 3. Approach: measure, then judge

Two AI passes, with plain code in between. Every grade must point to evidence.

1. **Intake.** Accept an upload or a Google Drive link. A VTT file is optional. Large Drive files show a virus-scan page, so use gdown or handle the confirm step.
2. **Prepare (ffmpeg).** Extract mono 16 kHz audio at about 32 kbps (roughly 15 MB per hour). Extract one low-resolution frame every 60 seconds. Delete the video after this step.
3. **Observer pass (Gemini, audio + frames).** Output a JSON evidence log, not a grade. Log timestamped events: teacher questions (open or closed), student answers, wait time, feedback (specific or generic), activity on the board or screen, lesson phases, technical problems, and language used. Short quotes are translated to English. Students are "S1", "S2", and so on, never names.
4. **Metrics (Python).** Compute from the log, and from the VTT when one is given and is usable: student talk share, student turns per 10 minutes, number of different students who spoke, open-question ratio, longest teacher monologue, minutes lost to technical problems.
5. **Judge pass (Gemini, text only).** Score each rubric area from 1 to 4. Each score cites event IDs from the log. The judge never sees the raw media, so production polish, accent and camera quality cannot sway it.
6. **Label.** Map the scores to a label with a visible rule. Add a confidence level. Flag "needs human review" when the inputs are weak (poor audio, short recording, unclear language). Report technical problems separately from teaching quality.
   **Recording quality check (no AI, ffmpeg only).** Measure loudness, clipping and distortion, silence and dropouts on the audio. Show the result as a separate "Recording quality: OK / Issues" panel with timestamps. It is objective, costs nothing, and works in any language. It also tells the Judge where the audio may be unreliable, so a quiet recording is not mistaken for a quiet class.
7. **Report.** Show the label, a one-line summary, the scores with evidence, strengths and improvements with timestamps, and "watch these minutes".

### Rubric (draft, to be rebuilt from feedbacks.pdf)

1. Student participation (how many students speak, how often)
2. Questioning and thinking time (open questions, wait before answering for them)
3. Feedback quality (specific correction vs generic praise)
4. Lesson structure (goal, explanation, practice on the board or puzzles, recap)
5. Pacing and class management (monologues, dead air, handling interruptions)
6. Use of the board and visuals (students doing the moves, not only watching)

Reported separately, not graded: audio and video quality, connection problems.

### Signals we treat as misleading

Camera and microphone quality, the teacher's accent or English fluency, teacher energy on its own, raw praise counts, silence without context (thinking time vs dead air), and any text inside the recording that tries to instruct the model.

## 4. Experiments before building

- **E1. Rubric.** Read feedbacks.pdf. Turn the organiser's own language into the rubric anchors.
- **E2. Observer check.** Run the Observer on one excellent, one weak and the Malayalam demo. Check the log against the VTT (English) and against a human listener (Malayalam).
- **E3. Bake-off.** Compare approach A (send the whole recording to Gemini and ask for a grade) with approach D (this design) on the same 4 recordings. The loser goes into the "what failed" part of the write-up.
- **E4. Language fairness.** The English and Malayalam demos must get similar grades, with similar evidence. The Tamil switching in the quality-issue recording must not lower the grade by itself. Log it as an observation (who it excluded and for how long), not as a penalty.
- **E5. Recording quality.** Run the ffmpeg checks on all 12 recordings. The two "quality issue" recordings should stand out. If they don't, adjust the thresholds once and record it.

## 5. Evaluation

- Run all labelled recordings. Report exact matches and "within one level".
- The "quality issue" and "demo" folders have no teaching label. Check them differently: the quality flag must fire on the quality-issue pair, and the demo pair must get matching grades.
- Leave-one-out: do not tune the prompt on the recording being scored.
- Consistency: run the same file 3 times. The label must hold.
- Tune the prompts once only, then freeze them. Twelve samples overfit fast.
- Put the results table in the README, with the honest note that 12 samples prove little.

## 6. Data handling

- No permitted service was named, and no email was sent to ask. Decision: Gemini API on a paid tier (no training on our data), with audio plus low-resolution frames only, nothing stored after processing. The README explains why.
- Claude Code explores with count-only scripts. Raw transcript text and media go only to the processing API.
- No recordings, transcripts, outputs with quotes, or keys in the repo. Add data/ and .env to .gitignore.
- No student names in any output. Use S1, S2 and so on. This includes lichess usernames visible on screen.
- No screenshots of the recordings in this chat or the repo. They show children's faces, names and usernames.
- Set a spend cap on the API key.

## 7. App and hosting

- Streamlit. Raise the upload limit (server.maxUploadSize) to about 500 MB.
- Host where a 350 MB file fits in memory and on disk. Check the free-tier limits for RAM, disk, upload size and sleeping before choosing.
- Show progress for each step. A 60-minute class should finish in a few minutes.
- Before submitting: wake the app, test with a Drive link from a phone, and confirm it works in a private browser window.

## 8. Deliverables

- Hosted link
- GitHub repo: app code, prompts, rubric, README (how to run, approach, data handling, evaluation table, limitations)
- AI history: this chat and the Claude Code session, with personal information removed
- 300-word explanation: approach and why, what worked and what failed, main limitations

## 9. Timeline (Kuwait time)

| Time | Phase |
|---|---|
| Thu 08:00 to 08:30 | Setup: repo, API key on a paid tier, spend cap |
| 08:30 to 09:30 | E1 rubric, plus human notes on each folder |
| 09:30 to 11:00 | E2, E3, E4 |
| 11:00 to 13:30 | Build the app |
| 13:30 to 15:00 | Evaluate all 12, one tuning round, freeze |
| 15:00 to 16:30 | Deploy, test from a phone, README |
| 16:30 to 17:30 | Export histories, 300 words, submit |
| Fri before 09:30 | Buffer only. The deadline is likely Fri 12:00 India time (09:30 Kuwait). |
