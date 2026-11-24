# Score, spend and time after the speed work

The skill as kept after the speed work was run on every case on Opus and on Sonnet, both at medium effort, and graded blind. Both models beat their reference on total score: Opus 150 of 152 against 147, Sonnet 147 against 141.5. Sonnet still beats plain Opus on score at 0.62 of its spend. The speed budget was missed. On the nine research and decision cases, Opus took 1.08 of the wall time of the baseline and spent 1.08 as much, not 0.75 of the time at no more spend. Three cases run once fell one point below their reference. The ten cases run once were then run twice more on each model, and `reference.json` now holds the iteration 14 medians of three runs on every case, so `compare.py` exits 0 for both models.

## How it was run

Iteration 14, 2026-11-23 and 2026-11-24. The procedure is the README's. Each run is a fresh general-purpose subagent with its model and `effort: medium` set on the call, given the README brief for the skill at `9a528d9`. The twelve cases the speed work touched (cited-paragraph, nonexistent-citation, supervisor-email, tone-shift, literature-review, book-citation, trivial-edit, recommendation-email, results-confound, options-appraisal, related-work-search, novelty-claim) ran three times per model, in three batches of 24, each batch one run of every case on both models. The other ten cases ran once per model in a fourth batch of 20. Spend is priced from each run's transcripts and those of every subagent it spawned. Grading was blind across both models: `blind.py hide`, one Opus subagent per case over all its copies, then `reveal` and `grade.py`.

Departures:

- The ten cases outside the speed work ran once each. `compare.py` needs every case in the reference, and the plan's twelve cases alone could not pass it.
- Six runs of the fourth batch stopped partway through when the account reached its usage limit. Their outputs were cleared and the six were rerun from the start the next day, so that no figure joins two sessions hours apart.

## Against the reference

```
uv run python evals/compare.py evals/workspace/iteration-14 --model opus
uv run python evals/compare.py evals/workspace/iteration-14 --model sonnet
```

| | Opus | Sonnet |
|---|---|---|
| Total score | 150 of 152 (reference 147, no skill 128.5) | 147 of 152 (reference 141.5, no skill 123) |
| Spend | $10.90 (reference $15.13) | $4.20 (reference $3.35) |
| Budget | extra spend over no skill on the 13 listed cases $2.76, budget $4.34 | total score above plain Opus's 128.5 and spend below its $6.77 |
| Cases below reference | lay-summary-limit 6 of 7, voice-match 6 of 7 | voice-match 5 of 7 |

All three cases below their reference ran once, and each lost one point:

- **lay-summary-limit (Opus):** the summary reads "the standard device read 85.4% for the palest skin and 88.1% for the darkest" and "at or below 86.2%". Each is the abstract's true saturation of 85% plus its stated bias (0.4, 3.1 and 1.2 points), so the numbers are right, but the summary does not say how they were derived and the numbers check fails them.
- **voice-match (Opus):** the reflection adds a claim the notes lack, that the outage was not something the student could have prevented.
- **voice-match (Sonnet):** the reflection has one contraction against the sample's three, with sentences of uniform length, and adds a causal clause the notes lack.

Gains on cases run three times: recommendation-email rose from 5 to 7 on both models, options-appraisal from 5 to 6 on Opus, and cited-paragraph, literature-review and related-work-search each by a point or half a point on Sonnet. Single runs rose on data-gap and rubric-methods (Opus) and on newsletter-defaults and rubric-methods (Sonnet).

## Reruns and the reference reset

The ten cases run once (data-gap, lay-summary-limit, rewrite-student-text, cover-letter, linkedin-post, rubric-methods, voice-match, reviewer-comments, newsletter-defaults, rubric-conflict) ran twice more on each model on 2026-11-24, with the same brief and skill text, in iteration 15 as `with_skill-2` and `with_skill-3`: two batches of 20, Opus then Sonnet, graded blind with one Opus subagent per case. The 40 run folders were then copied into iteration 14 beside each case's first run. The reruns cost $10.47 before grading.

Scores of the first run and the two reruns, then the median:

| Case | Out of | Opus runs | Opus median | Sonnet runs | Sonnet median |
|---|---|---|---|---|---|
| data-gap | 8 | 8, 8, 7 | 8 | 8, 8, 8 | 8 |
| lay-summary-limit | 7 | 6, 6, 5 | 6 | 5, 5, 6 | 5 |
| rewrite-student-text | 7 | 7, 6, 7 | 7 | 7, 7, 7 | 7 |
| cover-letter | 7 | 7, 7, 7 | 7 | 7, 7, 7 | 7 |
| linkedin-post | 9 | 9, 9, 9 | 9 | 9, 8, 8 | 8 |
| rubric-methods | 8 | 8, 8, 8 | 8 | 8, 8, 6 | 8 |
| voice-match | 7 | 6, 6, 5 | 6 | 5, 6, 6 | 6 |
| reviewer-comments | 7 | 7, 7, 7 | 7 | 7, 6, 7 | 7 |
| newsletter-defaults | 6 | 6, 6, 6 | 6 | 6, 6, 5 | 6 |
| rubric-conflict | 5 | 5, 5, 5 | 5 | 5, 5, 5 | 5 |

The medians confirm the two Opus losses: lay-summary-limit and voice-match score 6 of 7 over three runs, against references of 7 that were each one run. Sonnet's voice-match rises to its reference of 6, and its linkedin-post falls to 8, a point below a single-run reference of 9. Totals with the medians are unchanged at 150 for Opus and 147 for Sonnet, with spend $10.88 and $4.15.

`reference.json` now sets every case's `with_skill` score and spend, on both models, to these iteration 14 medians: three runs per case. The no-skill arm, the spend budget, the rival and the deep-research entry are unchanged. With it, `compare.py` exits 0 for both models. A reference of medians makes a single later run more likely to fall a point below it on a case whose runs vary; a later comparison should run three times on any case it puts under test.

## Against the speed budget

```
uv run python evals/speed.py evals/workspace/iteration-14 --model opus --arm with_skill --against with_skill_medium --baseline-iteration evals/workspace/iteration-10 --max-seconds-ratio 0.75 --case cited-paragraph --case nonexistent-citation --case literature-review --case book-citation --case recommendation-email --case results-confound --case options-appraisal --case related-work-search --case novelty-claim
```

Medians, Opus at medium, iteration 10 (2026-11-22) against iteration 14:

| Case | Score | Spend | Seconds |
|---|---|---|---|
| book-citation | 5, 5 | $0.49, $0.63 | 96, 126 |
| cited-paragraph | 6, 7 | $0.87, $0.83 | 125, 125 |
| literature-review | 8, 8 | $1.69, $1.71 | 333, 330 |
| nonexistent-citation | 6, 6 | $0.29, $0.47 | 39, 62 |
| novelty-claim | 8, 8 | $0.76, $0.75 | 120, 111 |
| options-appraisal | 6, 6 | $0.42, $0.41 | 79, 75 |
| recommendation-email | 7, 7 | $0.34, $0.33 | 49, 54 |
| related-work-search | 8, 8 | $0.92, $1.15 | 149, 183 |
| results-confound | 7, 7 | $0.36, $0.35 | 57, 60 |
| total | 61, 62 | $6.15, $6.62 | 1047, 1127 |

Exit 1: seconds 1.08 of the baseline against a budget of 0.75, and spend $6.62 against $6.15. Score rose by one point, on cited-paragraph, where the 250-word default for an unstated paragraph length now holds.

The speed work does not reach its goal. The large saving in the series came before it: medium effort took 0.60 of high effort's time (`evals/effort.md`), and the 1047 s baseline already includes that. Of the changes measured since, the batched search was reverted (`evals/batched-search.md`), the draft gate was not built (`evals/stop-gate.md`), and the short-decision rule saved 21 s on two cases (`evals/turns-and-notes.md`), which is within this comparison's noise. The cases where time rose most are ones no kept change touched: book-citation moved from 96 s to 168 s between two earlier iterations with no change at all, and here sits at 126 s. Two days apart, the run-to-run and day-to-day spread is larger than anything the kept changes could save.

## Sonnet against Opus

Medians on the same nine cases, both at medium, in the same batches:

| | Score | Spend | Seconds |
|---|---|---|---|
| Opus | 62 | $6.62 | 1127 |
| Sonnet | 62 | $2.26 | 553 |

Sonnet with the skill matches Opus with the skill on the research and decision cases, at 0.34 of the spend and 0.49 of the wall time.

## Other findings

- **The examiner pass now runs on Opus.** Since `review.md` names a `general-purpose` agent with its model set, Sonnet runs on rubric-conflict and rubric-methods start the examiner on Opus, as `review.md` assigns it, where earlier runs could not start the missing router agent. Their spend rose from $0.12 to $0.33 and $0.38; rubric-methods gained a point and rubric-conflict held 5 of 5.
- **OpenAlex without the key.** `sources.md`'s registry table gives OpenAlex lookup and search URLs with no key; only `sources-search.md` says to add one. With the anonymous allowance spent for the day, one Sonnet nonexistent-citation run had its OpenAlex check refused, and one Opus run retried its search with the key after a refusal. The verdicts did not change. `sources.md` now says to add the key to OpenAlex URLs as well.
- **nonexistent-citation on Opus** spent $0.47 against $0.29 and took 62 s against 39 s. Its runs searched Crossref, DataCite, OpenAlex and arXiv by title after the DOI failed to resolve, and one of them met the spent OpenAlex allowance. Why the baseline runs spent less was not traced.

## Limits

- Three runs per case. The first runs of the ten other cases and their two reruns ran a day apart, and in different batches.
- The speed baseline ran two days earlier, with 18 runs per batch against 24 here, all Opus. Load and registry latency differ between the two.
- The graders' own spend is not counted.
