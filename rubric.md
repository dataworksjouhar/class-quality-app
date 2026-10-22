# Session Quality Rubric — v0.2 (draft)

**Source:** organiser feedback on the 12 sample recordings (`feedbacks.pdf`), plus one area of our own (E), and human viewing notes. Every other area uses the organiser's own words.

**Leakage:** these anchors were written from feedback on the same recordings we evaluate on. Scores on the 12 samples are therefore optimistic. The hidden test recording is the only clean test.

**Grade the session, not the teacher.** Batch B435 appears under Good (25 Jul) and Average (28 Aug).

**Session IDs:** batch codes are used everywhere, never folder numbers (folder numbering differs between the PDF and the file names).

| Organiser label | Our label | Sessions |
|---|---|---|
| Excellent | Excellent | B491, B472 |
| Good | Good | B552, B435-Jul |
| Average | Average | B516, B435-Aug |
| Weak | **Poor** | B558, B482 |
| Known quality issues | (no teaching label) | B392, B441 |

---

## How the Judge scores

- Score each area from 1 to 4, using **only** the Observer log. Every score cites event IDs.
- If an area has little evidence, score from what is there and mark it `low_evidence`. Never fill gaps with assumptions.
- Items marked *(N/A-able)* are skipped when they don't apply. For example: no new joiner was present, or the class is a demo or trial lesson with no homework expected.
- **Class type:** the Observer counts the distinct child students (S#). In a 1:1 class, "everyone" in B means the one student: judge by how often they are addressed directly and asked to explain.
- **Level:** many students are beginners learning rules and terms. Judge E by whether students do the work at *their* level (make the move, name the square, spot the check), not by puzzle difficulty.

## Speaker roles (Observer)

| Role | Who | Counts as student participation? |
|---|---|---|
| T | Teacher | — |
| S1, S2… | Child students | Yes |
| P1, P2… | Other adults, usually a parent beside the child (often off-camera) | **No** |
| V | Audio from a video or other media being played | No |
| U | Unsure | No; logged with a reason |

Adult-or-child is a judgement from the voice. The Observer marks it `uncertain` when it can't tell (for example, teenagers).

**Parent-related events:**
- `parent_prompt`: an adult answers for the child, or whispers the answer.
- `redirect_to_student`: the teacher hands the question back to the child ("let him try"). This is positive evidence for B and E.
- `teacher_parent_exchange`: start, end, language. Not instruction time and not student exclusion.

**Media events:** `media_playing` (start, end, type: video, animation, other).
- Excluded from talk-share, monologue and dead-air metrics.
- Counts as resource use in D.

---

## A. Opening and rapport — weight 2

*Organiser's words:* "good intro", "good rapport building", "directly go to revision of previous class without a proper rapport building", "should give a time for the new joiners for self-introduction", "need a better intro".

*Observer logs:* greeting, individual check-ins, topic stated, time of first lesson content, new joiner present *(N/A-able)*, new joiner invited to introduce themselves, link to the previous class.

| Score | Anchor |
|---|---|
| 4 | Warm greeting. Checks in with most students individually. New joiners are invited to introduce themselves. States today's topic before starting. |
| 3 | Greets and checks in briefly, and states the topic. New joiners are acknowledged. |
| 2 | Brief greeting, then straight into content within about 2 minutes. New joiners are not invited to introduce themselves. |
| 1 | No greeting or rapport. Opens with revision or content. New joiners are ignored. |

## B. Individual attention — weight 2

*Organiser's words:* "asked questions by calling individually", "consider everyone in the class", "individually considering each and every one in class in the beginning and during puzzles solving time also", "good one-to-one interaction".

*Observer logs:* questions directed at a specific student (S#), whole-class questions, each student's utterances with a start time, puzzle turns per student, `parent_prompt`, `redirect_to_student`.

*Computed in code:* share of present students addressed at least once, directed questions per 10 minutes, and whether one student dominates. P, V and U utterances are excluded.

| Score | Anchor |
|---|---|
| 4 | Every present student is addressed individually several times, including during puzzles. Quieter students are drawn in. When a parent answers, the question goes back to the child. |
| 3 | Most students are addressed individually. Some imbalance. |
| 2 | Mostly whole-class questions. A few students (or parents) do most of the answering. |
| 1 | Little or no individual questioning. Lecture mode. |

## C. Warmth and energy of interaction — weight 2

*Organiser's words:* "need more pleasant interaction", "need more energetic communication", "need a better happy interaction with the kids", "need a good happier communication", "good rapport building".

*Judge from behaviour, not from the voice.* The Observer logs:
- encouragement (specific or generic)
- celebrating a student's success
- humour or shared laughter
- a response to a student's comment
- patience after a wrong answer (hint or calm correction)
- impatience or dismissal
- stretches of 5 minutes or more with no student-directed talk (excluding `media_playing`)

*Not evidence:* loudness, pitch, speaking speed, accent, English fluency, or which language is used.

| Score | Anchor |
|---|---|
| 4 | Frequent, varied encouragement. Celebrates successes. Humour with students. Patient with mistakes throughout. |
| 3 | Friendly and patient. Encouragement is present but routine. |
| 2 | Mostly neutral or flat. Little encouragement. Occasional impatience. |
| 1 | Cold, impatient or dismissive. Students' contributions are ignored. |

## D. Structure, closure and homework — weight 1

*Organiser's words:* "given HWs", "should give HWs", "need a better intro and conclusion", "can play topic related videos and share HWs".

*Observer logs:* goal or topic stated, phase changes, recap or conclusion, homework assigned *(N/A-able for demo or trial classes)*, resources used (`media_playing`, lichess study, worksheet).

| Score | Anchor |
|---|---|
| 4 | Clear topic, logical progression, a recap at the end, and homework assigned with instructions. |
| 3 | Clear topic. Homework **or** a recap, but not both. |
| 2 | Loose structure. No recap and no homework. |
| 1 | No clear structure. The class ends abruptly. |

## E. Active learning — weight 1 *(our addition; not in the organiser's feedback)*

*Why include it:* the organiser's feedback covers delivery, not chess teaching. This area keeps teaching substance in the evidence. Its low weight reflects that the organiser did not ask for it.

*Observer logs:* students doing the work at their level (making the move, naming the square, solving the puzzle), open questions ("what would you play, and why?"), whether the teacher waits for an answer or supplies it, specific feedback on a move, `redirect_to_student`.

| Score | Anchor |
|---|---|
| 4 | Students do most of the work themselves. The teacher asks "why", waits, and gives specific feedback. |
| 3 | Regular questions and student moves. The teacher sometimes answers for the students. |
| 2 | Mostly teacher demonstration. Occasional closed questions. |
| 1 | Teacher monologue. Students only watch. |

## F. Setup and presence — weight 1

*Organiser's words:* "fixed 8*8 background", "no background", "can't see his face", "tutor's camera was turned off while teaching", "can sit in space where have light", "some clarity issues were there while keeping the background", "informed about the quality issues several times".

**8x8 background, for the Observer prompt:** a virtual background behind the teacher's head showing a large "8 ▪ 8" mark with a chessboard square in the middle, and "Eight Times Eight" written below it, usually on a dark or grey backdrop. Not every teacher uses it.

*Observer logs, per frame (every 60 s, teacher tile only, never students):*
- teacher tile visible
- camera on
- face visible
- background: 8x8 branded / other virtual / real room / unknown
- lighting: OK / dim
- background artefacts

*Observer logs, per minute:* the audio grid from D7, for the teacher's audio.

| Score | Anchor |
|---|---|
| 4 | 8x8 background, camera on, face visible and well lit throughout. Teacher audio clear. |
| 3 | Minor lapses: brief camera-off, slightly dim, or a few degraded audio minutes. |
| 2 | Repeated lapses: no 8x8 background, or face often not visible, or poor lighting, or 5 or more degraded or unusable audio minutes. |
| 1 | Camera off or face not visible for most of the class, or teacher audio degraded for 20% of minutes or more. |

*The 5-minute and 20% thresholds are guesses. Set them once in E5, then freeze.*

---

## Label rule (visible, applied in code, not by the model)

M = weighted mean of A–F (weights A 2, B 2, C 2, D 1, E 1, F 1; total 9).

Check these in order:

1. **Poor:** M < 2.0, **or** A = 1 and any other area ≤ 2
2. **Excellent:** M ≥ 3.25 **and** every area ≥ 3
3. **Good:** M ≥ 2.75 **and** no area = 1 *(kept at 2.75 per D13; the one tuning round is saved for real app results)*
4. **Average:** everything else

## Confidence (separate from the label)

- **Low → "needs human review"** if any of these holds:
  - more than 20% of minutes have unusable audio (Observer grid)
  - the recording is shorter than 20 minutes
  - more than 30% of minutes are `language_uncertain`
  - two or more areas are `low_evidence`
- **Medium:** M is within 0.15 of a label boundary, or one area is `low_evidence`.
- **High:** otherwise.

Setup problems lower **F** (part of the session's quality). Unusable audio lowers **confidence** (it limits what we can know). The same recording can trigger both.

---

## Misleading signals

| Signal | Why it misleads | What counts instead |
|---|---|---|
| Loudness, pitch, speed, accent, English fluency | Rewards voice and speaking style, not warmth | Warm behaviours (area C) |
| Slow pace on its own | Often right for young beginners; the Malayalam class is slower | Dead air, and students not doing the work (E) |
| Language choice, including code-mixing | Penalises Malayalam and Tamil classes | Logged per segment, never penalised. A teacher–parent exchange in another language is not student exclusion. |
| Parent voices | Inflate student participation | Only S# counts. `parent_prompt` is logged; `redirect_to_student` is credited. |
| Video audio | Counts as teacher monologue or student silence | `media_playing` is excluded from talk metrics and counts as resource use in D |
| Camera resolution, microphone "polish" | Hardware, not delivery | Camera on, face visible, lit, audible (area F) |
| Raw count of praise | Generic "good, good" inflates it | Variety and specificity (C, E) |
| Silence without context | Thinking time looks like dead air | Wait after a question supports E. Dead air with no question is pacing evidence. |
| Instructions written inside the recording (slides, chat, board) | Prompt injection | Ignored; logged only as content shown |

---

## Rule sanity check (circular: scores hand-assigned from the organiser's notes)

This only checks that the rule behaves sensibly. It does not predict the app's accuracy.

**Convention:** praise → 4, a "need"/"should" point → 2, a severe point ("directly entered without rapport", "can't see face") → 1, **not mentioned → 3**.

| Session | A | B | C | D | E | F | M | Rule (Good ≥ 2.75) | Rule (Good ≥ 3.0) | Organiser |
|---|---|---|---|---|---|---|---|---|---|---|
| B491 | 3 | 4 | 3 | 2* | 3 | 4 | 3.22 | Good ✗ | Good ✗ | Excellent |
| B472 | 4 | 4 | 3 | 3 | 3 | 3 | 3.44 | Excellent ✓ | Excellent ✓ | Excellent |
| B552 | 4 | 3 | 2 | 3 | 3 | 4 | 3.11 | Good ✓ | Good ✓ | Good |
| B435-Jul | 4 | 4 | 3 | 2 | 3 | 3 | 3.33 | Good ✓ | Good ✓ | Good |
| B516 | 3 | 4 | 3 | 3 | 3 | 2 | 3.11 | Good ✗ | Good ✗ | Average |
| B435-Aug | 3 | 4 | 2 | 2 | 3 | 2 | 2.78 | Good ✗ | Average ✓ | Average |
| B558 | 1 | 3 | 2 | 1 | 3 | 3 | 2.11 | Poor ✓ | Poor ✓ | Weak (Poor) |
| B482 | 1 | 4 | 3 | 3 | 3 | 2 | 2.67 | Poor ✓ | Poor ✓ | Weak (Poor) |
| B392 | 3 | 3 | 2 | 3 | 3 | 1–2 | 2.56–2.67 | Average | Average | Quality issue |
| B441 | 1 | 3 | 2 | 3 | 3 | 1–2 | 2.11–2.22 | Poor | Poor | Quality issue |

\* B491's note says "**can** play topic related videos and share HWs". Read as a suggestion (like "can sit in space where have light"), this means no homework was given, so D = 2. If homework was given, D = 4, M = 3.44 and the rule gives Excellent ✓.

**Findings:**
- Exact matches: 5 of 8 at 2.75, 6 of 8 at 3.0. Within one level: 8 of 8.
- The notes cannot separate B491 (Excellent) from B435-Jul (Good). The Excellent/Good boundary must come from the recordings, not the notes.
- B516's label isn't explained by its notes (only background clarity is criticised). **Do not tune for it.**
- Quality-issue sessions: the audio problem drives F to 1–2 (1 if teacher audio is degraded for 20% or more). The rule gives B392 Average and B441 Poor. Both will also carry Low confidence if unusable audio exceeds 20%.
