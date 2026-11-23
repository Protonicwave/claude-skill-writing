# Fewer turns and shorter decision notes

Five changes to the skill text were run against the skill before them, on Opus at medium effort, on seven cases, three runs per arm, every pair in the same batch. Together they scored 46 against 45 and took 0.97 of the wall time, but spent 1.04 times as much ($2.54 against $2.45). Taken apart, the short-decision rule paid and the one-message rule did not, so the one-message rule was reverted. The other three changes fix faults rather than save time, and stay.

## The changes

- **One message for independent calls** (`SKILL.md`, Effort): read everything the tier names, and send every independent call, in one message. Reverted.
- **Short decisions** (`registers/decision.md`, Length): a decision under 400 words gets three yes/no tests and a judgement log of the three choices the student is likeliest to reverse. Kept.
- **A default paragraph length** (`SKILL.md`, Decisions): a single paragraph with no length set is at most 250 words. Kept.
- **Review passes as general-purpose agents** (`review.md`): the passes named `router-worker`, `router-scout` and `router-expert`, which exist only where the model-router plugin is installed; they now name a `general-purpose` agent with its model (Sonnet, Haiku or Opus) set on the call. Kept.
- **The OpenAlex key in typed searches** (`sources-search.md`): add `&api_key=$OPENALEX_API_KEY` to every OpenAlex URL when the variable is set. Kept.

## How it was run

Iteration 13, 2026-11-23. Each run is a fresh general-purpose subagent with `model: opus` and `effort: medium`, given the README brief. `with_skill_before` read the skill as of `e359516`, extracted outside the repository; `with_skill_turns` read the branch's skill at `2cc7b40`, with all five changes. Cases: cited-paragraph, for the paragraph default; supervisor-email, tone-shift and trivial-edit, the light cases the one-message rule could slow or speed; recommendation-email, results-confound and options-appraisal, the decision and analysis cases. Two arms, three runs each: 42 runs, in three batches of 14, each batch one run of every case in both arms. Both arms' briefs told the executor to add `api_key=$OPENALEX_API_KEY` to any OpenAlex URL it requested itself, so the key change is not measured here. The runs were graded blind, one Opus grader per case.

## Score, spend and time, every run

Each cell is score, spend and wall time for runs 1, 2 and 3.

| Case | Before | After the changes |
|---|---|---|
| cited-paragraph | 6, $0.56, 95 s; 7, $0.70, 118 s; 7, $1.05, 189 s | 7, $0.64, 101 s; 7, $0.77, 117 s; 7, $1.04, 161 s |
| supervisor-email | 6, $0.21, 29 s; 6, $0.18, 23 s; 6, $0.19, 26 s | 7, $0.19, 27 s; 6, $0.18, 22 s; 7, $0.18, 24 s |
| tone-shift | 6, $0.22, 29 s; 6, $0.21, 28 s; 6, $0.23, 32 s | 6, $0.21, 29 s; 6, $0.22, 27 s; 6, $0.23, 33 s |
| trivial-edit | 6, $0.15, 13 s; 6, $0.16, 17 s; 6, $0.15, 17 s | 6, $0.15, 14 s; 6, $0.15, 15 s; 6, $0.15, 17 s |
| recommendation-email | 7, $0.35, 60 s; 7, $0.31, 56 s; 7, $0.27, 46 s | 7, $0.33, 58 s; 7, $0.27, 43 s; 7, $0.32, 55 s |
| results-confound | 7, $0.37, 66 s; 7, $0.35, 62 s; 7, $0.35, 56 s | 6, $0.44, 78 s; 7, $0.43, 74 s; 7, $0.34, 56 s |
| options-appraisal | 6, $0.49, 99 s; 6, $0.54, 112 s; 6, $0.54, 106 s | 6, $0.41, 79 s; 6, $0.48, 87 s; 6, $0.52, 94 s |

```
uv run python evals/speed.py evals/workspace/iteration-13 --model opus --arm with_skill_turns --against with_skill_before --max-seconds-ratio 1.0
```

Summed medians: score 45 before and 46 after, spend $2.45 and $2.54, time 413 s and 400 s, a ratio of 0.97. Exit 1, on spend.

## What each change did

- **Short decisions.** On the two decision cases, the only ones the rule reaches, the summed medians fell from $0.84 to $0.80 and from 162 s to 141 s (0.87), at 13 points in both arms. Options-appraisal, the longer of the two, gained most: $0.54 to $0.48 and 106 s to 87 s.
- **One message.** Across all 42 runs, tool turns were 174 before and 176 after, while tool calls rose from 226 to 263 and turns carrying more than one call from 44 to 59. Runs grouped calls they would have made anyway and added more, but did not finish in fewer turns. On the five cases outside the decision rule, time was 1.03 and spend 1.09 of the before arm. results-confound, where only this rule applied, rose from $0.35 to $0.43 and from 62 s to 74 s, and two of its runs took 15 and 19 tool turns against 10 or 11. Reverted in `a5f61c4`.
- **Paragraph default.** One before run of cited-paragraph failed its hidden 250-word check; no after run did. The default is a logged choice and costs one `--max-words` flag on a command already run.
- **General-purpose review agents.** One after run of cited-paragraph spawned its claim-support pass as a Sonnet `general-purpose` agent, and it started. No run in either arm was refused a subagent.
- **supervisor-email** gained a point in two after runs on the check that every number appears in the inputs: those runs replaced the past date "16 November" with a marker. The before runs did the same in their notes but kept the number in the email. This is a difference in how the runs treated a stale date, not an effect of any change, and the gain is not counted for any of them.

## Limits

Three runs per arm move a median by one run. The decision cases' saving (21 s, $0.04) is larger than the spread between their runs, but the light cases' figures differ by a second or a cent, within it. The kept configuration has not been run as a whole: the next full rerun measures it.
