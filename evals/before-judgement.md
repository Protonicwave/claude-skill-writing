# Score and spend before the judgement changes

The skill as it stood on `feat/judgement` before any change to `writing/`, run on all twenty cases for both models, with and without the skill, and graded blind. Opus with the skill scored 131 of 136 against 115.5 for plain Opus. Sonnet with the skill scored 126.5 against 114 for plain Sonnet, and 115.5 for plain Opus. Opus with the skill spent $5.42 more than plain Opus on the thirteen original cases. Sonnet with the skill spent $2.65 across the twenty cases, against $5.49 for plain Opus.

## How it was run

Iteration 5, on 2026-11-19. Each run was a general-purpose subagent with its model set explicitly, given the brief in `README.md`. Spend is list price from the run's own transcripts and those of every subagent it spawned, at the prices in `reference.json`. Every judgement expectation was graded blind by an Opus subagent per case, which saw only the case's prompt, input files, expectations and the unlabelled copies; the key stayed outside the iteration until all 92 copies were graded. Programmatic checks were scored by `grade.py` after the key was applied.

Twelve Opus runs were not rerun, because their transcripts could be matched to their stored outputs by the delivered text. With the skill, from iteration 4: cases 13, 8, 4, 9, 5 and 7. Without the skill, from the iteration-2 control run: cases 8, 4, 9, 5, 7 and 12. Every other run is new: all of Sonnet's, Opus on cases 14 to 20, and Opus on the cases whose old transcript was missing or matched more than one agent (2, 3, 6, 12 with the skill; 2, 3, 6, 13 without). Cases 1, 10 and 11 ran twice per arm on both models, because their spend has varied by more than 25% between runs; the median counts. This differs from the plan, which copied every iteration-4 run: it also copied only one arm, because iteration 4 holds no plain-Opus runs.

Expectation counts per case are those in `evals.json`. The old Opus reference was graded by the author of the skill; this one is graded blind, so differences of one expectation are as likely to come from the grader as from the skill.

## Score and spend

| Case | Opus, skill | Opus, plain | Spend | Plain | Sonnet, skill | Sonnet, plain | Spend | Plain |
|---|---|---|---|---|---|---|---|---|
| 1 cited-paragraph | 7/7 | 5.5/7 | $1.27 | $0.39 | 6.5/7 | 5/7 | $0.19 | $0.10 |
| 2 nonexistent-citation | 6/6 | 5/6 | $0.42 | $0.32 | 6/6 | 5/6 | $0.19 | $0.09 |
| 3 data-gap | 7/8 | 6/8 | $0.36 | $0.21 | 8/8 | 7/8 | $0.10 | $0.08 |
| 4 lay-summary-limit | 7/7 | 4/7 | $0.59 | $0.25 | 5/7 | 4/7 | $0.13 | $0.08 |
| 5 rewrite-student-text | 7/7 | 7/7 | $0.37 | $0.17 | 7/7 | 7/7 | $0.11 | $0.07 |
| 6 supervisor-email | 7/7 | 5/7 | $0.28 | $0.17 | 7/7 | 7/7 | $0.10 | $0.07 |
| 7 tone-shift | 6/6 | 6/6 | $0.24 | $0.15 | 6/6 | 4/6 | $0.11 | $0.07 |
| 8 cover-letter | 7/7 | 6/7 | $0.40 | $0.21 | 7/7 | 6/7 | $0.12 | $0.08 |
| 9 linkedin-post | 9/9 | 8/9 | $0.28 | $0.19 | 9/9 | 9/9 | $0.16 | $0.07 |
| 10 literature-review | 8/8 | 6.5/8 | $2.76 | $0.85 | 7/8 | 5/8 | $0.30 | $0.09 |
| 11 rubric-methods | 7/8 | 6.5/8 | $1.35 | $0.26 | 7/8 | 7/8 | $0.12 | $0.09 |
| 12 voice-match | 7/7 | 6/7 | $0.27 | $0.17 | 6/7 | 7/7 | $0.10 | $0.08 |
| 13 book-citation | 5/5 | 5/5 | $0.74 | $0.57 | 5/5 | 4/5 | $0.16 | $0.08 |
| 14 reviewer-comments | 7/7 | 7/7 | $0.50 | $0.19 | 7/7 | 7/7 | $0.12 | $0.08 |
| 15 newsletter-defaults | 6/6 | 5/6 | $0.42 | $0.21 | 5/6 | 4/6 | $0.11 | $0.08 |
| 16 trivial-edit | 6/6 | 5/6 | $0.15 | $0.17 | 5/6 | 5/6 | $0.08 | $0.07 |
| 17 rubric-conflict | 5/5 | 5/5 | $0.74 | $0.20 | 5/5 | 5/5 | $0.12 | $0.08 |
| 18 recommendation-email | 5/7 | 5/7 | $0.39 | $0.23 | 5/7 | 5/7 | $0.12 | $0.08 |
| 19 results-confound | 7/7 | 7/7 | $0.43 | $0.31 | 7/7 | 6/7 | $0.11 | $0.08 |
| 20 options-appraisal | 5/6 | 5/6 | $0.97 | $0.29 | 6/6 | 5/6 | $0.11 | $0.10 |
| Total | 131/136 | 115.5/136 | $12.93 | $5.49 | 126.5/136 | 114/136 | $2.65 | $1.61 |

## Budgets

- Budget 1, Opus with the skill, extra spend over plain Opus on cases 1 to 13: $5.42 measured. `reference.json` holds 80% of it, $4.34. `compare.py --model opus` therefore exits 1 on this iteration, by $1.08, and the skill changes that follow must close that gap.
- Budget 2, Sonnet with the skill, spend below plain Opus across twenty cases: $2.65 against $5.49, and a score of 126.5 against 115.5. `compare.py --model sonnet` exits 0 now; the rival lines are already met, so the later rerun has to keep them met while the skill changes.

Three cases carry most of Opus's extra spend: literature-review ($1.91), rubric-methods ($1.09) and cited-paragraph ($0.88), 3.88 of the 5.42 dollars. The literature review and the cited paragraph are the cases that search for and verify sources; rubric-methods adds the examiner and cold-reader passes.

## What the figures show

- Sonnet with the skill beats plain Sonnet by 12.5 expectations and plain Opus by 11, at 48% of plain Opus's spend. It is below its own plain arm in one case, voice-match (6 against 7), and ties it in eight others.
- On the new cases 14 to 20, Opus with the skill beats plain Opus in cases 15 and 16 only, and ties the other five. Sonnet with the skill beats plain Sonnet in 15, 19 and 20, and ties 14, 16, 17 and 18. The cases for judgement and analysis therefore do not yet separate the skill from the plain model; the decision rules and the new registers are the changes meant to.
- Case 18 (recommendation-email) scores 5 of 7 in all four arms, so something in its expectations is missed by every arm. The grader's evidence is in each copy's `grading.json` under `evals/workspace/iteration-5/`, which git ignores.
- Opus with the skill spends less than plain Opus in case 16 ($0.15 against $0.17), the case written to score restraint on spend. Sonnet with the skill spends $0.08 against $0.07.
- Against the old Opus reference, data-gap and rubric-methods are one expectation lower (7 of 8 each) and supervisor-email is one higher. The reference now holds these figures, so no case is below its reference on this iteration.
- Runs of the same case differ in spend by up to 25%: literature-review with the skill cost $2.61 and $2.90 on Opus and $0.25 and $0.34 on Sonnet.

## Limits

- Spend counts the runs' own transcripts. Requests a tool makes outside them, such as a web search's own model call, are not counted, and the with-skill arms search more.
- Twelve of the Opus runs are from earlier iterations, graded now with the same blind procedure but run under the earlier session's conditions.
- One Sonnet run (case 9, with the skill) wrote a stray file into `evals/workspace/` and deleted it; another run left three stray files there, which were removed. Neither touched `outputs/`.
- One Sonnet plain-arm run (case 8) read the git user name to sign its letter. The deliverable was graded as written.
