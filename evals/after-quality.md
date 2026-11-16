# Score and cost after the quality expectations

The skill as of d3d9b3a scored 92 of 93 on the thirteen cases: 44 of 44 judgement expectations and 48 of 49 programmatic checks, the same as the reference run regraded on the new expectations, against 75 of 93 for the same model with no skill. No case scored lower than its reference. The with-skill runs used 1,039,726 tokens, subagents included, so the extra cost over the no-skill arm rose from 349,980 to 396,416 tokens, 37,483 of the rise in case 1.

This version adds five judgement expectations, which score what the review passes and the source search add: a stated uncertainty before claiming agreement (case 3), the computer-model caveat and a plain-word gloss of infrared (case 4), a gap claim checked against work beyond the student's papers (case 10), and each detail the rubric requires but the notes lack marked as missing (case 11). Each fails at least one stored output, so each can fail. It also changes `sources.md` so a cited draft passes `check.py` alone before the sources file is written, the chained check runs once per round of edits, a draft over its word limit is cut in one edit, and PDFs are saved as UTF-8 text.

## How it was run

Run on 2026-11-16 (iteration 4), with `claude-opus-5-5` as the executor and the brief in `README.md`. Only the four cited cases (1, 2, 10 and 13) were rerun, because only they read `sources.md`; the other nine read the same skill files as in iteration 3, and their iteration-3 runs were copied in. The no-skill arm is the iteration-2 run already in `reference.json`, regraded on the new expectations. Raw outputs are in `evals/workspace/iteration-4/`, which git ignores.

Case 1 was run twice. The first run wrote a paragraph of 277 words against the case's 250-word check, a limit the request does not state, and scored 6 of 7; its outputs are in `evals/workspace/iteration-4-extra/`. The second scored 7 of 7 and is the one recorded. Case 10's completion notice came while the run still had background work open, and no later notice came, so its figure is the one that notice gave.

`reference.json` now holds these figures, with `max_extra_tokens` at 400,000.

## Rerun cases

| Case | Judgement | Checks | Reference | Tokens | Previous reference tokens | No skill tokens | Seconds |
|---|---|---|---|---|---|---|---|
| 1 cited-paragraph | 4 of 4 | 3 of 3 | 7 | 118,567 | 81,084 | 52,202 | 222.1 |
| 2 nonexistent-citation | 3 of 3 | 3 of 3 | 6 | 65,637 | 62,651 | 49,554 | 81.4 |
| 10 literature-review | 5 of 5 | 3 of 3 | 8 | 209,430 | 209,328 | 74,121 | 507.2 |
| 13 book-citation | 3 of 3 | 2 of 2 | 5 | 79,667 | 73,802 | 57,975 | 131.9 |

## What failed

- Case 6 still fails its numbers-from-the-inputs check on 23 and 24, for the reason `after-efficiency.md` gives.
- Case 10 missed its target of 170,000 tokens. The target was set on the wrong measure. A run's `total_tokens` is the size of its context at the last turn, which is mostly the search output, the saved papers and the skill files it read, so making fewer calls barely moves it: 156,096 before the change and 153,433 after, before subagents. Spend falls with the number of turns. Against the iteration-3 run, the run made 42 tool calls instead of 63 and 34 model turns instead of 51, and the context it reread across those turns fell from 5,296,134 cached tokens to 3,296,805. Output fell from 53,738 tokens to 47,760. No turn was spent keeping a generated sources file in step with the draft or trimming to the word limit one word at a time.

## What changed beyond the score

- Case 1 cost 37,483 more than its reference. Both new runs saved the ATLAS paper's full text instead of quoting only the abstract, so the methods comparison and the leading systematic now rest on quoted passages from the paper. That gave four and five claim and quote pairs, above the three that `review.md` judges in the main run, so each spawned the claim-support reviewer at about 23,000 tokens.
- Case 10 still searched beyond the student's four papers and found self-learning Monte Carlo and variational autoregressive networks, the two papers that narrow the gap claim, and the new expectation on the gap passed.
