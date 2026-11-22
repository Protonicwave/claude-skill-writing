# The skill against deep research, after the gap search

The skill with the gap search (a bounded, recorded registry search for published work that replaces or changes a stated gap) run against Anthropic's deep-research skill on the six research cases, three runs per arm per model, graded blind. The target was met: on every research case the skill's median score is at least deep research's and its median spend is lower, on both models, and the gap search's extra spend is inside its budget. `compare.py --against deep_research` exits 0 for Opus and for Sonnet.

## How it was run

Iteration 9, 2026-11-21 and 2026-11-22. The procedure is the README's. Each run is a fresh general-purpose subagent with its model set explicitly, given the README brief for its arm: `with_skill` follows the skill, `deep_research` invokes `anthropic-skills:deep-research` and not the skill, and `without_skill` (cases 21 and 22 only) is the plain model. Six cases (1, 2, 10, 13, 21, 22), two models, three runs per arm: 84 runs. Spend is priced from each run's own transcripts and those of every subagent it spawned, at the list prices in `reference.json`. Grading was blind: `blind.py hide`, one Opus subagent per half case (six or nine copies each), then `reveal` and `grade.py`.

Departures from the plan:

- The network dropped while the six first Sonnet deep-research runs were in progress. All six, with their researcher subagents, ended on an API error. Their partial outputs were deleted and each was run once more. The records below are the reruns.
- Runs of both arms wrote stray files into the repository root (empty `reports/` and `research_notes/` folders, an empty `references-log.md`, a `notes.md` from a failed run). They were removed. One run reported overwriting an untracked `arxiv.xml` in the root; git showed a clean tree before the runs, so no tracked file changed.
- Deep research hit its 20-concurrent-subagent limit in several Opus runs. In those, a researcher was started late or the run did that part itself, as its notes record. This is how the arm behaves when twelve of them run together.
- A copy's contents can reveal its arm to a grader (the skill writes `gap-search.md` and `references-log.md`; deep research writes `reports/`). Blinding hides the labels, not the style.

## Score and spend, every run

Each cell is score and spend for runs 1, 2 and 3. The medians are in the next table.

### Opus

| Case | With skill | Deep research | Plain |
|---|---|---|---|
| cited-paragraph | 7/7 $1.13, 7/7 $0.97, 7/7 $1.16 | 5/7 $4.15, 4/7 $4.69, 5/7 $3.95 | not run |
| nonexistent-citation | 6/6 $0.47, 6/6 $0.46, 6/6 $0.46 | 4/6 $1.88, 4/6 $2.03, 4/6 $2.24 | not run |
| literature-review | 8/8 $2.74, 8/8 $2.42, 8/8 $1.80 | 7/8 $4.67, 6/8 $4.07, 6/8 $4.09 | not run |
| book-citation | 5/5 $0.90, 5/5 $0.73, 5/5 $0.88 | 5/5 $2.09, 5/5 $1.94, 5/5 $1.89 | not run |
| related-work-search | 8/8 $1.27, 8/8 $1.78, 8/8 $1.02 | 5/8 $5.53, 5/8 $2.53, 6/8 $4.67 | 7/8 $0.85, 6/8 $0.74, 7/8 $0.80 |
| novelty-claim | 8/8 $0.96, 8/8 $0.68, 8/8 $0.93 | 5/8 $3.60, 5/8 $3.25, 5/8 $2.71 | 6/8 $0.55, 6/8 $0.27, 6/8 $0.47 |

### Sonnet

| Case | With skill | Deep research | Plain |
|---|---|---|---|
| cited-paragraph | 7/7 $0.41, 7/7 $0.37, 7/7 $0.35 | 5/7 $0.39, 5/7 $0.59, 5/7 $0.53 | not run |
| nonexistent-citation | 6/6 $0.14, 6/6 $0.11, 6/6 $0.12 | 5/6 $0.26, 4/6 $0.26, 4/6 $0.23 | not run |
| literature-review | 8/8 $0.38, 8/8 $0.31, 8/8 $0.40 | 6/8 $0.81, 7/8 $0.69, 6/8 $0.89 | not run |
| book-citation | 5/5 $0.18, 5/5 $0.18, 5/5 $0.17 | 5/5 $0.40, 5/5 $1.00, 5/5 $0.52 | not run |
| related-work-search | 7/8 $0.54, 7/8 $0.35, 8/8 $0.44 | 6/8 $1.22, 5/8 $1.37, 4/8 $1.07 | 5/8 $0.12, 5/8 $0.10, 5/8 $0.08 |
| novelty-claim | 8/8 $0.27, 8/8 $0.20, 8/8 $0.25 | 6/8 $0.79, 6/8 $0.62, 6/8 $1.25 | 4/8 $0.09, 4/8 $0.10, 4/8 $0.07 |

## Medians against deep research

`compare.py evals/workspace/iteration-9 --model <model> --against deep_research`, both exit 0.

| Case | Opus skill | Opus deep research | Sonnet skill | Sonnet deep research |
|---|---|---|---|---|
| cited-paragraph | 7/7 $1.13 | 5/7 $4.15 | 7/7 $0.37 | 5/7 $0.53 |
| nonexistent-citation | 6/6 $0.46 | 4/6 $2.03 | 6/6 $0.12 | 4/6 $0.26 |
| literature-review | 8/8 $2.42 | 6/8 $4.09 | 8/8 $0.38 | 6/8 $0.82 |
| book-citation | 5/5 $0.88 | 5/5 $1.94 | 5/5 $0.18 | 5/5 $0.52 |
| related-work-search | 8/8 $1.27 | 5/8 $4.67 | 7/8 $0.44 | 5/8 $1.22 |
| novelty-claim | 8/8 $0.93 | 5/8 $3.25 | 8/8 $0.25 | 6/8 $0.79 |

Gap search spend on literature-review, the median with-skill spend less the figure before the gap search:

- Opus: $2.42 against a baseline of $2.76, so the extra spend is $-0.34 against a budget of $1.02 (25% of deep research's $4.09). Met, because this iteration's runs cost less than the reference runs.
- Sonnet: $0.38 against a baseline of $0.30, so the extra spend is $0.08 against a budget of $0.20 (25% of deep research's $0.82). Met.

## Plain arm on the new cases

Cases 21 and 22 ran a plain arm, three runs per model. Medians: Opus 7 of 8 at $0.80 on related-work-search and 6 of 8 at $0.47 on novelty-claim; Sonnet 5 of 8 at $0.10 and 4 of 8 at $0.09. The skill scores 1 to 4 expectations higher for 1.6 to 4.4 times the spend. These figures, and the with-skill medians for both cases, are now in `reference.json`.

## What the figures show

- The skill met the user's condition on every research case: a score at least equal to deep research's median and a lower median spend, on both models. Its spend is 23% to 59% of deep research's on Opus and 32% to 70% on Sonnet.
- Deep research's losses are mostly on things the skill does by rule, not on whether the research found the right facts. By failures across its runs: it broke the word limit in 17 of the 24 runs where one applies (counted by `check.py`: 250 words on cited-paragraph and novelty-claim, 500 on literature-review, 310 on related-work-search); it saved no `verify.py` log on cited-paragraph (6 of 6) and no record of the registries searched on novelty-claim and related-work-search (6 of 6 each); it left the student's own contribution unmarked on novelty-claim (6 of 6); it stated what a cited work did without a saved passage in 5 of 6 related-work-search runs and 4 of 6 literature-review runs; and on nonexistent-citation it left no `[UNVERIFIED]`-style marker in 6 of 6.
- It did find the false claims. On literature-review, related-work-search and novelty-claim its deliverables said that published work already replaces the sampler, uses circuit-level noise or applies reinforcement learning to tokamak control. The score gap is therefore about traceability and restraint, which is what the skill is for, not about missing the research.
- book-citation is a tie on score on both models (5 of 5 each). Both arms caught that no 7th edition is dated 2004. The skill wins there on spend only.
- With skill, the only expectations missed were Sonnet related-work-search's passage support in one run and its four-works count in one run.

## Limits

- Three runs per arm is the least that gives a median against the spread seen here. Deep research's spend varied by up to a factor of two between runs of one case, and a one-expectation difference is as likely to come from the grader as from the arm.
- Deep research's spend is understated: a web search's own fee is not in the transcripts, and `spend.py` cannot see it.
- Deep research was run with its researcher subagents, and under a 20-subagent cap that twelve concurrent runs reached, so some runs of that arm did part of the research themselves.
- The grader is an Opus subagent, and the skill's file names can show it which arm a copy came from. The expectations and word limits were written for the skill's own conventions (a verification log, markers, a stated length), and the deep-research brief did not state them, so part of its gap is the arm not knowing the house rules. It is still the result the user asked for: the skill's output is the one that can be traced and trusted.
- Cases 21 and 22 were written for this comparison and checked against planted outputs; they were not tuned against deep research's output.
- The Opus gap-search budget is met because iteration 9's literature-review runs cost less than the reference runs, not because the gap search is free: it adds one search call and the lines that narrow the claim.
