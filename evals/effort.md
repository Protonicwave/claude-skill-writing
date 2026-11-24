# The skill on Opus at medium and at high effort

The skill run on Opus at medium effort against Opus at high effort on the six research cases and the three decision cases, three runs per arm, graded blind. Medium took 0.60 of high's wall time and 0.70 of its spend, and scored 61 of 62 against 62. The one point lost is a word count on a paragraph whose length the user did not state, not a judgement expectation. Opus runs the skill at medium effort.

## How it was run

Iteration 10, 2026-11-22. The procedure is the README's. Each run is a fresh general-purpose subagent with `model: opus` and its effort set on the call: `with_skill_high` at high, `with_skill_medium` at medium, both given the README brief for the skill. Nine cases (1, 2, 10, 13, 18 to 22), two arms, three runs each: 54 runs. The runs went in three batches of 18, each batch one run of every case in both arms, so machine and network load fell on both arms alike. Spend is priced from each run's transcripts and those of every subagent it spawned. Wall time is the span of those transcripts' timestamps. Grading was blind: `blind.py hide`, one Opus subagent per case over its six copies, then `reveal` and `grade.py`.

Departures from the README:

- The brief asked each run to say whether any subagent it tried to start was refused, to tell a refused review pass from a skipped one.
- `blind.py` accepted only `with_skill`, `without_skill` and `deep_research` arms. It now also accepts a skill arm named for its variant, such as `with_skill_medium`.

## Score, spend and time, every run

Each cell is score, spend and wall time for runs 1, 2 and 3.

| Case | High | Medium |
|---|---|---|
| book-citation | 5/5 $0.69 181 s, 5/5 $0.68 140 s, 5/5 $0.81 194 s | 5/5 $0.49 96 s, 5/5 $0.54 92 s, 5/5 $0.49 105 s |
| cited-paragraph | 7/7 $0.85 143 s, 6/7 $1.86 328 s, 7/7 $1.11 206 s | 6/7 $0.63 99 s, 6/7 $1.18 184 s, 6/7 $0.87 125 s |
| literature-review | 8/8 $2.45 487 s, 8/8 $2.81 541 s, 8/8 $1.92 369 s | 8/8 $1.73 333 s, 8/8 $1.52 295 s, 8/8 $1.69 360 s |
| nonexistent-citation | 5/6 $0.59 85 s, 6/6 $0.58 91 s, 6/6 $0.49 72 s | 6/6 $0.29 38 s, 6/6 $0.30 41 s, 6/6 $0.29 39 s |
| novelty-claim | 8/8 $1.05 197 s, 7/8 $1.11 194 s, 8/8 $0.68 124 s | 7/8 $0.76 124 s, 8/8 $0.81 120 s, 8/8 $0.75 114 s |
| options-appraisal | 6/6 $0.68 140 s, 6/6 $0.64 138 s, 6/6 $0.57 129 s | 6/6 $0.42 79 s, 6/6 $0.53 94 s, 6/6 $0.40 75 s |
| recommendation-email | 7/7 $0.38 73 s, 7/7 $0.42 78 s, 7/7 $0.44 76 s | 7/7 $0.39 60 s, 7/7 $0.32 49 s, 7/7 $0.34 49 s |
| related-work-search | 8/8 $1.74 332 s, 8/8 $1.44 305 s, 8/8 $1.41 261 s | 8/8 $0.71 129 s, 8/8 $1.05 183 s, 7/8 $0.92 149 s |
| results-confound | 7/7 $0.41 78 s, 7/7 $0.37 69 s, 7/7 $0.44 82 s | 7/7 $0.42 73 s, 7/7 $0.36 57 s, 7/7 $0.30 43 s |

## Medians

`uv run python evals/speed.py evals/workspace/iteration-10 --model opus --arm with_skill_medium --against with_skill_high --max-seconds-ratio 0.75` exits 1, on the cited-paragraph score alone.

| Case | High | Medium |
|---|---|---|
| book-citation | 5 $0.69 181 s | 5 $0.49 96 s |
| cited-paragraph | 7 $1.11 206 s | 6 $0.87 125 s |
| literature-review | 8 $2.45 487 s | 8 $1.69 333 s |
| nonexistent-citation | 6 $0.58 85 s | 6 $0.29 39 s |
| novelty-claim | 8 $1.05 194 s | 8 $0.76 120 s |
| options-appraisal | 6 $0.64 138 s | 6 $0.42 79 s |
| recommendation-email | 7 $0.42 76 s | 7 $0.34 49 s |
| related-work-search | 8 $1.44 305 s | 8 $0.92 149 s |
| results-confound | 7 $0.41 78 s | 7 $0.36 57 s |
| total | 62 $8.80 1751 s | 61 $6.15 1047 s |

Medium's median is faster and cheaper on every case.

## What was lost, and why medium was chosen

Every expectation missed, by arm:

- High: one judgement expectation (nonexistent-citation run 1 added the sentence as "has been reported to superconduct at room temperature" with an `[UNVERIFIED]` marker, which the grader read as presenting the result) and two word counts (cited-paragraph at 286 words and novelty-claim at 265, against 250).
- Medium: one judgement expectation (related-work-search run 3 cited three machine-learning decoders where four are expected) and four word counts (cited-paragraph at 251, 254 and 255 words, novelty-claim at 300).

The judgement expectations are level, one miss in 27 runs each. Medium's extra losses are all word counts on the two cases whose request states no length, where the skill sets no default for a single paragraph and the eval checks 250 words. High misses the same check in two of six runs on those cases, once by 36 words, so more effort does not fix it: the runs land either side of a limit they were never told. The plan's rule was to name a case medium loses as a place for high effort. That would buy back a word-count coin toss at the price of 67% more time and 43% more spend on every such run. A default length for an unstated paragraph, checked with `check.py --max-words`, is the fix; it is a skill change and belongs with the turn and notes cuts.

So Opus runs the skill at medium, with no case named for high effort, and medium is the baseline the later speed changes are measured against.

## Other findings

- The review table in `review.md` hands passes to `router-worker`, `router-scout` and `router-expert`. No such agent type is registered where the evals ran. Runs fell back to `general-purpose` or `Explore`, or judged the pass themselves; two runs, one per arm, first asked for the missing type and lost a turn on it. Nine high runs and eight medium runs started a reviewer, so this does not favour either arm, but it costs every run that reaches a review pass.
- Two options-appraisal runs at high and one at medium reached the checker's third run still over 400 words, cut by hand and delivered without a fourth check. All three passed the word limit when graded, but the length was not confirmed when they were delivered.
- One high cited-paragraph run made 64 tool calls over 328 s, against 21 to 33 calls for the other five runs of the case. It is the slowest run of the case in either arm and does not change either median.

## Limits

- Three runs per arm. A one-point difference on a case is within the grader's and the model's run-to-run spread; the word counts that decided cited-paragraph were 1 to 5 words over.
- Wall time includes queueing behind 17 other concurrent runs and the registries' response times. Both arms shared each batch, so the ratio is fairer than either figure alone.
- Only Opus was run. Sonnet's effort is set in a later iteration.
