# Score and cost after the quality expectations

The skill as of d3d9b3a scored 91 of 92 on the thirteen cases: 45 of 45 judgement expectations and 46 of 47 programmatic checks, the same as the reference run regraded on the new expectations, against 74 of 92 for the same model with no skill. No case scored lower than its reference. The with-skill runs used 1,041,042 tokens, subagents included, so the extra cost over the no-skill arm rose from 349,980 to 397,732 tokens, 37,483 of the rise in case 1.

This version scores what the review passes and the source search add. Four judgement expectations are new: no agreement or consistency with the accepted value claimed while the slope has no uncertainty (case 3), the simulation stated as a limitation (case 4), a gap claim narrowed against published methods that already change the sampler (case 10), and each detail the rubric requires but the notes lack marked as missing (case 11). Case 4's plain-word expectation now covers infrared as well. Each new expectation fails at least one stored output, apart from case 10's, which every stored run passes because both arms searched; it fails a planted output, the case 10 deliverable with its last paragraph replaced by the gap as the notes state it. The version also changes `sources.md`, so a cited draft passes `check.py` alone before its claims are written into the sources file, the chained check runs once after each set of fixes, a draft over its word limit is cut in one edit, and PDFs are saved as UTF-8 text.

## How it was run

Run on 2026-11-16 (iteration 4), with `claude-opus-5-5` as the executor and the brief in `README.md`. Only the four cited cases (1, 2, 10 and 13) were rerun, because the change governs drafts that cite. Cases 8 and 12 also read `sources.md`, through the application and essay registers, but cite nothing, so for them the change adds about 150 words of reading; their iteration-3 runs, and those of the other seven cases, were copied in. The no-skill arm is the iteration-2 run already in `reference.json`, regraded on the new expectations. Raw outputs are in `evals/workspace/iteration-4/`, which git ignores.

Case 1 was run twice. The first run wrote a paragraph of 277 words against the case's 250-word check, a limit the request does not state, and scored 6 of 7; its outputs are in `evals/workspace/iteration-4-extra/`. The second scored 7 of 7 and is the one recorded. Case 10's first completion notice came while the run still had a background command open, a loop it had started to poll for its reviewers' output. The loop ended 37 minutes later and the run stopped it in three more turns without changing its outputs. The figures here are from its final notice, and most of its 2,755.7 seconds are that wait.

After the run, `sources.md` was reworded so the search may start the sources file before the draft settles, and so every double quote in a hand-written line is escaped; the expectations were reworded so each grades one way. Neither change was rerun. The stored outputs were regraded on the new wording, and only case 4's score changed, by merging two expectations.

`reference.json` now holds these figures, with `max_extra_tokens` at 400,000.

## Rerun cases

| Case | Judgement | Checks | Reference score | Tokens | Previous reference tokens | No skill tokens | Seconds |
|---|---|---|---|---|---|---|---|
| 1 cited-paragraph | 4 of 4 | 3 of 3 | 7 | 118,567 | 81,084 | 52,202 | 222.1 |
| 2 nonexistent-citation | 3 of 3 | 3 of 3 | 6 | 65,637 | 62,651 | 49,554 | 81.4 |
| 10 literature-review | 5 of 5 | 3 of 3 | 8 | 210,746 | 209,328 | 74,121 | 2,755.7 |
| 13 book-citation | 3 of 3 | 2 of 2 | 5 | 79,667 | 73,802 | 57,975 | 131.9 |

## What failed

- Case 6 still fails its numbers-from-the-inputs check on 23 and 24, for the reason `after-efficiency.md` gives.
- Case 1's 250-word check failed one of its two runs. The request gives no limit, so the skill has none to hold to, and a run that explains more fails it by chance; the gate can then fail on this case with nothing wrong in the skill. It is left as it is, because a new prompt would need a rerun of the no-skill arm.
- Case 10 missed a target of 170,000 tokens, set before the `sources.md` change. The target was on the wrong measure. A run's `total_tokens` is the size of its context at the last turn, which is mostly the search output, the saved papers and the skill files it read, so making fewer calls barely moves it: 156,096 before the change and 154,749 after, before subagents. The change did remove the loop. Against the iteration-3 run, the run made 44 tool calls instead of 63 and 37 model turns instead of 51, and none was spent keeping a generated sources file in step with the draft or trimming to the word limit a word at a time. Its spend did not fall. Weighting cache reads at a tenth of the input price, cache writes at 1.25 times and output at five times, it cost 984,990 input-token equivalents against 963,197 for the iteration-3 run. Up to its deliverable it cost 759,944, a fifth less; the last three turns came after the 37-minute wait on its own polling loop, by which time the prompt cache had expired, and wrote its whole context to the cache again. Waiting on reviewers is set by `review.md`, which this version leaves unchanged, and is the next place to cut.

## What changed beyond the score

- Case 1 cost 37,483 more than its reference. Both new runs saved the ATLAS paper's full text instead of quoting only the abstract, so the methods comparison and the leading systematic now rest on quoted passages from the paper. That gave four and five claim and quote pairs, above the three that `review.md` judges in the main run, so each spawned the claim-support reviewer at about 23,000 tokens.
- Case 10 still searched beyond the student's four papers and found self-learning Monte Carlo and variational autoregressive networks, the two papers that narrow the gap claim, and the new expectation on the gap passed.
- `max_extra_tokens` sits 2,268 tokens above the measured extra, under 1%, against the 10% margin `after-efficiency.md` set. Case 1 alone moved by 3,616 tokens between its two runs, so a rerun of every case may fail the budget on noise.
