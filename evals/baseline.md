# Baseline score

The skill as merged in 1bbe8c7 scored 55 of 62: 27 of 28 judgement expectations and 28 of 34 programmatic checks. Later versions of the skill must score at least as well on every case.

## How it was run

Run on 2026-11-11, one run per case (iteration 1), with `claude-opus-5-5` as the executor. Each case ran in a fresh general-purpose subagent given the brief below, with no access to `evals.json`. The programmatic checks were scored by `evals/grade.py`; the judgement expectations were graded by reading each deliverable, its notes and any verification log. Raw outputs are in `evals/workspace/iteration-1/`, which git ignores.

```
You are running one test case of a writing skill. Act on the request below exactly as you would for a real user, following the skill.

Skill: read <repo>/writing/SKILL.md first and follow it, reading the other skill files it points to as you need them. Use this copy, not any installed copy. Its scripts are in <repo>/writing/scripts/.

The user's request, in their words:
"<prompt>"

The user's files: <absolute paths, or none>

Output directory: <repo>/evals/workspace/iteration-<N>/<eval name>/with_skill/outputs/
- Save the text you would deliver, exactly as delivered, to outputs/deliverable.md.
- Save what you would tell the user after the text (open markers, judgement calls, where logs are) to outputs/notes.md.
- Save every other file you create (sources file, verification log, saved pages, drafts) in outputs/.

There is no user to answer questions. Where the skill says to ask, take the most reasonable reading and record the question in notes.md. Do not open anything else under <repo>/evals/ apart from the user's files above.

Reply with one line: done, or failed and why.
```

## Scores

| Case | Judgement | Checks | Tokens | Seconds |
|---|---|---|---|---|
| 1 cited-paragraph | 4 of 4 | 2 of 3 | 80,416 | 143.5 |
| 2 nonexistent-citation | 3 of 3 | 3 of 3 | 62,223 | 61.9 |
| 3 data-gap | 3 of 3 | 3 of 4 | 64,685 | 66.8 |
| 4 lay-summary-limit | 3 of 3 | 1 of 3 | 61,328 | 75.1 |
| 5 rewrite-student-text | 3 of 3 | 4 of 4 | 61,318 | 45.7 |
| 6 supervisor-email | 3 of 3 | 3 of 4 | 51,177 | 19.6 |
| 7 tone-shift | 2 of 3 | 3 of 3 | 51,923 | 28.5 |
| 8 cover-letter | 3 of 3 | 4 of 4 | 62,584 | 69.6 |
| 9 linkedin-post | 3 of 3 | 5 of 6 | 62,619 | 54.3 |
| Total | 27 of 28 | 28 of 34 | 558,273 | 565.0 |

## What failed

- Case 1, at most 250 words: 328. The paragraph itself is within the limit, but the deliverable also carried an unrequested BibTeX entry.
- Case 3, numbers from the inputs: 0.1, the reading precision inferred from the peaks being given to one decimal place.
- Case 4, at most 200 words: 202 by the grader's count, 198 by the run's own count. Numbers from the inputs: 85.4 and 88.1, which are 85 plus the 0.4 and 3.1 point biases. Both are correct and disclosed in the notes, but the check counts any derived number.
- Case 6, numbers from the inputs: 17, the date of the Tuesday, derived from Monday 16 November and disclosed in the notes.
- Case 7, no individual blamed: "could whoever made it run them and fix the loader?" still points at the person who pushed, and "I've already debugged this twice" keeps the reproach.
- Case 9, at most 50% one-sentence paragraphs: 4 of 6.

Three of the six check failures are derived numbers the run disclosed. The check stays strict because a derived number and an invented one look the same to code; the notes are where a reader tells them apart.

## What the runs showed beyond the score

- No case invented a number, source or result. Every gap was marked, and both citation cases ran `verify.py`: case 1 verified the ATLAS paper and quoted its abstract and full text, and case 2 found the DOI unregistered and refused the claim.
- Cases 8 and 9 had no register to use. Both runs fell back on the message register and said so in their notes.
- Case 7 is the one judgement failure, and it is a tone request: the skill has no guidance on changing tone yet.
