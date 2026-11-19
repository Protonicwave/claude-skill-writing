# Score and spend after the judgement changes

The skill after the judgement changes (decide and log choices, read by effort tier, new decision and results registers), run with the skill on all twenty cases for both models and graded blind. The targets set for these changes were not both met. Opus with the skill scored 131.5 of 136 against 115.5 for plain Opus, and spent $6.66 more than plain Opus on the thirteen original cases, against a budget of $4.34. Sonnet with the skill scored 126 against 115.5 for plain Opus and spent $3.77 against $5.49, so its two rival conditions hold, but three cases fall below their reference.

## How it was run

Iteration 6, on 2026-11-19, with the same procedure as `before-judgement.md`: a general-purpose subagent per run with its model set, spend priced from its own transcripts and those of every subagent it spawned, graded blind by an Opus subagent per case. Cases 1, 10 and 11 ran twice per model, and the median counts. Only the with-skill arms were rerun; the plain arms are the iteration-5 figures held in `reference.json`.

Two differences from iteration 5 affect spend. The briefs were saved to files and each run began by reading its own brief, which adds one turn per run, and each run's final reply went through a hand-back call. A rerun of five cases in iteration 7 gave the briefs inline, as in iteration 5. Spend did not fall (see below), so these differences do not explain the increase.

## Score and spend, iteration 6

| Case | Opus | Spend | Reference | Sonnet | Spend | Reference |
|---|---|---|---|---|---|---|
| 1 cited-paragraph | 7/7 | $1.14 | $1.27 | 7/7 | $0.34 | $0.19 |
| 2 nonexistent-citation | 6/6 | $0.90 | $0.42 | 6/6 | $0.18 | $0.19 |
| 3 data-gap | 8/8 | $0.46 | $0.36 | 8/8 | $0.13 | $0.10 |
| 4 lay-summary-limit | 5/7 | $0.71 | $0.59 | 5/7 | $0.15 | $0.13 |
| 5 rewrite-student-text | 7/7 | $0.42 | $0.37 | 7/7 | $0.14 | $0.11 |
| 6 supervisor-email | 7/7 | $0.35 | $0.28 | 7/7 | $0.10 | $0.10 |
| 7 tone-shift | 6/6 | $0.44 | $0.24 | 6/6 | $0.11 | $0.11 |
| 8 cover-letter | 7/7 | $0.99 | $0.40 | 7/7 | $0.17 | $0.12 |
| 9 linkedin-post | 9/9 | $0.49 | $0.28 | 8/9 | $0.13 | $0.16 |
| 10 literature-review | 7.5/8 | $2.24 | $2.76 | 7/8 | $0.41 | $0.30 |
| 11 rubric-methods | 8/8 | $1.10 | $1.35 | 7/8 | $0.31 | $0.12 |
| 12 voice-match | 7/7 | $0.48 | $0.27 | 7/7 | $0.13 | $0.10 |
| 13 book-citation | 5/5 | $0.83 | $0.74 | 5/5 | $0.24 | $0.16 |
| 14 reviewer-comments | 7/7 | $0.61 | $0.50 | 5/7 | $0.15 | $0.12 |
| 15 newsletter-defaults | 5/6 | $0.55 | $0.42 | 4/6 | $0.13 | $0.11 |
| 16 trivial-edit | 5/6 | $0.20 | $0.15 | 5/6 | $0.09 | $0.08 |
| 17 rubric-conflict | 5/5 | $0.88 | $0.74 | 5/5 | $0.42 | $0.12 |
| 18 recommendation-email | 7/7 | $0.66 | $0.39 | 7/7 | $0.14 | $0.12 |
| 19 results-confound | 7/7 | $0.56 | $0.43 | 7/7 | $0.14 | $0.11 |
| 20 options-appraisal | 6/6 | $0.74 | $0.97 | 6/6 | $0.17 | $0.11 |
| Total | 131.5/136 | $14.76 | $12.93 | 126/136 | $3.77 | $2.65 |

Plain Opus scored 115.5 for $5.49 and plain Sonnet 114 for $1.61.

## Budgets

- Budget 1, Opus with the skill, extra spend over plain Opus on cases 1 to 13: $6.66 measured against $4.34. It was $5.42 before the changes, so it rose by about $1.24 where the target was a fall of 20%.
- Budget 2, Sonnet with the skill, spend below plain Opus and score at least plain Opus's: $3.77 against $5.49 and 126 against 115.5. Met.
- Cases below their reference: Opus lay-summary-limit (5 against 7), literature-review (7.5 against 8), newsletter-defaults (5 against 6) and trivial-edit (5 against 6); Sonnet linkedin-post (8 against 9), reviewer-comments (5 against 7) and newsletter-defaults (4 against 5).

## Rerun after one change to the skill

Failures on newsletter-defaults and trivial-edit came from the notes: a default's length was named without saying the student could change it, and a one-word edit's notes ran to four sentences. `SKILL.md` was changed so the judgement log says how to change each choice and a literal edit gets one or two sentences and no log (commit `645c903`, still 800 words). The five cases that fell below reference on either model were rerun once per model, with inline briefs.

| Case | Opus | Spend | Sonnet | Spend |
|---|---|---|---|---|
| newsletter-defaults | 6/6 | $0.52 | 6/6 | $0.18 |
| trivial-edit | 6/6 | $0.29 | 5/6 | $0.14 |
| lay-summary-limit | 5/7 | $0.80 | 4/7 | $0.21 |
| reviewer-comments | 6/7 | $0.86 | 7/7 | $0.15 |
| linkedin-post | 9/9 | $0.51 | 9/9 | $0.18 |

- newsletter-defaults is back at or above reference on both models, and linkedin-post and Sonnet's reviewer-comments recover. These are single runs, graded blind, so a difference of one expectation is within the grader's noise.
- trivial-edit on Sonnet still writes notes of three sentences. On Opus it costs $0.29, against $0.17 plain, so the case written to score restraint on spend is still more expensive with the skill.
- lay-summary-limit is below reference on both models. Opus's own failure is that the summary never says its figures come from a simulation. Its automatic check also fails on 85.4, 88.1 and 100, which are correct derivations from the abstract (85 plus 0.4, 85 plus 3.1, and 10^8 written as 100 million) that the number check cannot match.
- Opus reviewer-comments (6 of 7) fails only the automatic check that every number appears in the input: it flags 10.18434, 19, 2026, 30, 4.886, 5.12 and 78. Plain Opus passed that check in iteration 5.
- Spend rose in nine of the ten reruns against iteration 6, so the briefs in files did not cause the increase. Runs of one case varied by up to 45% in earlier iterations, so one run per case cannot show a real difference.

## What the figures show

- The skill's score advantage held. Opus with it beats plain Opus by 16 expectations, and Sonnet with it beats plain Opus by 10.5 at 69% of plain Opus's spend.
- The decision and results registers raised the new analysis cases: recommendation-email rose from 5 to 7 on both models, and options-appraisal and data-gap rose on Opus.
- The judgement changes did not cut spend. Turn counts and the amount the skill makes the model read are what drive it, and no change in these changes cuts either. Cover-letter on Opus ran an examiner pass on a 316 word letter, because the advert acts as a rubric, and rubric-conflict on Sonnet took 16 turns against 5.
- Plain-arm figures are from iteration 5, so a model-side change since then is not controlled for.

## Limits

- One run per case in the rerun, and two in the noisy cases of iteration 6.
- Spend counts the runs' own transcripts. A web search's own model call is not counted, and the with-skill arms search more.
- The grader is an Opus subagent that sees no arm labels but is a model: one expectation either way is as likely to come from the grader as from the skill.
- Cover-letter, literature-review and rubric-conflict show where spend sits. Reducing it means changing which files the tiers read and when a pass runs, which these changes did not do.
