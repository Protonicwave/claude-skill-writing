# The batched source search against the per-claim search

The skill with the batched source search (`find_sources.py`, one call for every claim, and the rewritten `sources-search.md`) run against the skill before it, on Opus at medium effort, on the six research cases, three runs per arm, every pair in the same batch. The batched search took 1.11 times the wall time and 1.09 times the spend. Every case that searched was slower and dearer; only book-citation and nonexistent-citation, which never call the search, were faster. The search was reverted. The concurrent verifier and the OpenAlex budget handling stay.

## How it was run

Iteration 12, 2026-11-23. Each run is a fresh general-purpose subagent with `model: opus` and `effort: medium`, given the README brief. `with_skill_before` read the skill as of `b704642` (before any search work), extracted outside the repository; `with_skill_search` read the branch's skill at `a8bfbf0`. Six cases, two arms, three runs each: 36 runs, in six batches of six, each batch one run of three cases in both arms, so registry and machine load fell on both arms alike.

Departures from the README:

- OpenAlex's anonymous allowance (1,000 credits a day, 10 per search) was spent, and the before arm cannot send a key. Its extracted `verify.py` was patched to add `OPENALEX_API_KEY` to OpenAlex requests, which `gap_search.py` shares, and both arms' briefs gained one line telling the executor to add `api_key=$OPENALEX_API_KEY` to any OpenAlex URL it requests itself. The 36 runs used about 1,070 keyed credits.
- The runs were not graded. The phase keeps a change only if its time ratio is at most 0.9 and its spend is no higher; both failed, and no score can reverse that, so grading would have cost money without changing the decision.

An earlier attempt, iteration 11 (18 runs of the search arm only, against iteration 10's `with_skill_medium`), gave 1.78 times the time and 1.23 times the spend, but its runs met OpenAlex and arXiv rate limits from 18 sessions sharing one address, and ran on a different day from its baseline. The control above replaces it.

## Spend and time, every run

Each cell is spend and wall time for runs 1, 2 and 3.

| Case | Before | Batched search |
|---|---|---|
| book-citation | $0.69 183 s, $0.50 95 s, $0.60 199 s | $0.57 174 s, $0.71 128 s, $0.48 122 s |
| cited-paragraph | $0.78 118 s, $1.01 155 s, $0.78 111 s | $0.74 139 s, $0.94 187 s, $1.14 186 s |
| literature-review | $1.73 320 s, $1.73 306 s, $1.62 308 s | $2.02 360 s, $1.88 340 s, $1.70 274 s |
| nonexistent-citation | $0.34 51 s, $0.44 64 s, $0.54 77 s | $0.31 46 s, $0.36 50 s, $0.34 46 s |
| novelty-claim | $0.59 92 s, $0.82 130 s, $0.62 95 s | $0.69 114 s, $0.70 109 s, $0.58 91 s |
| related-work-search | $1.26 206 s, $1.19 198 s, $0.99 165 s | $1.45 264 s, $1.36 215 s, $1.52 303 s |

## Medians

| Case | Before | Batched search | Spend ratio | Time ratio |
|---|---|---|---|---|
| book-citation | $0.60 183 s | $0.57 128 s | 0.95 | 0.70 |
| cited-paragraph | $0.78 118 s | $0.94 186 s | 1.21 | 1.57 |
| literature-review | $1.73 308 s | $1.88 340 s | 1.09 | 1.10 |
| nonexistent-citation | $0.44 64 s | $0.34 46 s | 0.77 | 0.71 |
| novelty-claim | $0.62 95 s | $0.69 109 s | 1.10 | 1.14 |
| related-work-search | $1.19 198 s | $1.45 264 s | 1.22 | 1.33 |
| Total | $5.35 967 s | $5.86 1074 s | 1.09 | 1.11 |

## Why it lost

The batched search did not cut the number of tool calls, which drives both time and spend. Median calls per run, before against batched: cited-paragraph 24 and 33, related-work-search 32 and 44, literature-review 43 and 48, novelty-claim 19 and 22. The search arm wrote a `claims.json` of one or two claims on cited-paragraph, whose notes name the one paper to cite, and five or six on related-work-search, then still read, fetched and verified source by source. Saving a few registry round trips cannot pay for that. Why the calls rose is not settled by these runs; the likeliest cause is the larger block of hits each search returns, every claim at once with abstracts, which the executor then works through.

## What stays

- `verify.py` checks up to four sources at once within each registry's limits: 4.9 s against 7.4 s on the fifteen sources of `verify_timing.jsonl`, measured on its own.
- `verify.py` sends `OPENALEX_API_KEY` to OpenAlex only, and fails at once on a wait of an hour or more rather than retrying through a spent daily budget.
- `speed.py --case` and `verify_timing.py`.
