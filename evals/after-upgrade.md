# Score after the upgrade

The skill as of 9eb3889 scored 58 of 62: 28 of 28 judgement expectations and 30 of 34 programmatic checks, against 55 of 62 at baseline (`baseline.md`). No case scored lower than at baseline.

This version adds the fresh-context review passes (`review.md`), tones (`voice.md`), the application and post registers, and the draft audit, outline and citation chasing in the process and in `sources.md`.

## How it was run

Run on 2026-11-11 (iteration 2), one run per case, with `claude-opus-5-5` as the executor and the brief in `baseline.md` unchanged. Programmatic checks were scored by `evals/grade.py`; judgement expectations were graded by reading each deliverable, its notes and any log. Raw outputs are in `evals/workspace/iteration-2/`, which git ignores.

Case 9 ran twice. The first run scored 2 of 3 on judgement: the post register then kept every unpublished result out of a public post, so the run left out the student's own 94.1% accuracy and the post had no concrete result. 9eb3889 narrowed the rule to results that belong to someone else, and the second run, scored below, gave the result and flagged the data question in its notes. The first run is kept as `linkedin-post/with_skill-first/`.

## Scores

| Case | Judgement | Checks | Baseline | Tokens | Seconds |
|---|---|---|---|---|---|
| 1 cited-paragraph | 4 of 4 | 2 of 3 | 4, 2 | 112,126 | 313.5 |
| 2 nonexistent-citation | 3 of 3 | 3 of 3 | 3, 3 | 70,127 | 81.8 |
| 3 data-gap | 3 of 3 | 3 of 4 | 3, 3 | 76,836 | 118.7 |
| 4 lay-summary-limit | 3 of 3 | 2 of 3 | 3, 1 | 92,381 | 241.7 |
| 5 rewrite-student-text | 3 of 3 | 4 of 4 | 3, 4 | 66,254 | 51.8 |
| 6 supervisor-email | 3 of 3 | 3 of 4 | 3, 3 | 53,439 | 23.2 |
| 7 tone-shift | 3 of 3 | 3 of 3 | 2, 3 | 55,409 | 35.6 |
| 8 cover-letter | 3 of 3 | 4 of 4 | 3, 4 | 77,915 | 168.0 |
| 9 linkedin-post | 3 of 3 | 6 of 6 | 3, 5 | 59,182 | 55.2 |
| Total | 28 of 28 | 30 of 34 | 27, 28 | 663,669 | 1089.5 |

## What failed

- Case 1, at most 250 words: 435. The paragraph itself is over the limit this time, not a BibTeX entry beside it. The run revised after the claim-support and cold-reader passes, and the glosses and reasoning it added made the paragraph longer.
- Case 3, numbers from the inputs: 0.1, the recording precision, as at baseline.
- Case 4, numbers from the inputs: 85.4 and 88.1 (derived, disclosed, as at baseline) and 100, from "100 million" for the abstract's 10^8.
- Case 6, numbers from the inputs: 12 and 17, the dates of the Thursday and Tuesday, derived from today's date and disclosed.

All three number failures are derived values the runs disclosed in their notes, as at baseline.

## What changed beyond the score

- Case 7, the one baseline judgement failure, passes: the post makes the change the subject instead of the person who pushed it, and drops the reproach.
- Cases 8 and 9 used their own registers. The cover letter mapped each criterion to the notes and left the one with no evidence as a marker; the post kept whole paragraphs and three hashtags.
- Case 1 ran the draft audit (no findings) and wrote its bibliography with `--bib`, outside the delivered text.
- Cost rose by 19% in tokens (558,273 to 663,669) and time nearly doubled (565 s to 1090 s). Most of the rise is in cases 1, 3, 4 and 8, the ones where review passes ran; cases 4 and 8 record them as fresh subagents. The token figures are the runs' own and may leave out what those nested subagents used, so the true rise may be larger.
- Case 2 ran `verify.py` only by recording a claim and quote for a paper that does not exist, because the verifier requires at least one quote per source. A reference supplied without a passage cannot be checked for existence alone.
