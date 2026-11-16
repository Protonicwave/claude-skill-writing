# Score and cost after the efficiency work

The skill as of 25e769a scored 87 of 88 on the thirteen cases: 39 of 39 judgement expectations and 48 of 49 programmatic checks, against 83 of 88 for the previous reference run and 74 of 88 for the same model with no skill. No case scored lower than its reference. The with-skill runs used 993,290 tokens, subagents included, against 1,314,855 for the previous reference, so the extra cost over the no-skill arm fell from 671,545 to 349,980 tokens. On the nine original cases it fell from 403,111 to 139,478.

This version cuts `SKILL.md` to 800 words, splits searching for sources from verifying them, has each register name the files it needs, adds `check.py --max-words` and `--inputs`, and runs each review pass only where it pays: the cold reader on long drafts and every explainer, on a smaller model; claim support as a subagent only above three claim and quote pairs.

## How it was run

Run on 2026-11-16 (iteration 3), one run per case, with `claude-opus-5-5` as the executor and the brief in `README.md`. Only the with-skill arm ran; the no-skill arm is the iteration-2 run recorded in `reference.json`. Programmatic checks were scored by `evals/grade.py`, which counts words for a limit on the prose, as `check.py --max-words` does; the no-skill arm was regraded the same way and kept its 74 of 88; judgement expectations were graded by reading each deliverable, its notes and any log. Tokens are each run's own total plus the subagents it listed in `outputs/subagents.json`. Raw outputs are in `evals/workspace/iteration-3/`, which git ignores.

`reference.json` now holds these figures, with `max_extra_tokens` at 385,000, the measured extra plus 10%. The target set before the work was 300,000; the run missed it, and the reference was reset to the measured figure.

## Scores

| Case | Judgement | Checks | Reference | Tokens | Reference tokens | No skill tokens | Seconds |
|---|---|---|---|---|---|---|---|
| 1 cited-paragraph | 4 of 4 | 3 of 3 | 6 | 81,084 | 181,877 | 52,202 | 136.5 |
| 2 nonexistent-citation | 3 of 3 | 3 of 3 | 6 | 62,651 | 70,127 | 49,554 | 71.0 |
| 3 data-gap | 3 of 3 | 4 of 4 | 6 | 53,445 | 98,398 | 45,716 | 45.6 |
| 4 lay-summary-limit | 3 of 3 | 3 of 3 | 5 | 85,619 | 114,358 | 47,483 | 125.9 |
| 5 rewrite-student-text | 3 of 3 | 4 of 4 | 7 | 63,308 | 66,254 | 44,722 | 49.8 |
| 6 supervisor-email | 3 of 3 | 3 of 4 | 6 | 52,305 | 53,439 | 43,696 | 41.8 |
| 7 tone-shift | 3 of 3 | 3 of 3 | 6 | 50,848 | 55,409 | 43,856 | 31.3 |
| 8 cover-letter | 3 of 3 | 4 of 4 | 7 | 58,017 | 122,915 | 46,212 | 79.1 |
| 9 linkedin-post | 3 of 3 | 6 of 6 | 9 | 51,049 | 59,182 | 45,407 | 43.9 |
| 10 literature-review | 4 of 4 | 3 of 3 | 7 | 209,328 | 199,502 | 74,121 | 537.0 |
| 11 rubric-methods | 3 of 3 | 4 of 4 | 6 | 101,042 | 156,340 | 47,240 | 182.3 |
| 12 voice-match | 3 of 3 | 4 of 4 | 7 | 50,792 | 57,739 | 45,126 | 41.1 |
| 13 book-citation | 3 of 3 | 2 of 2 | 5 | 73,802 | 79,315 | 57,975 | 123.3 |
| Total | 39 of 39 | 48 of 49 | 83 | 993,290 | 1,314,855 | 643,310 | 1508.6 |

## What failed

- Case 6, numbers from the inputs: 23 and 24. The prompt asks for Monday 16 November, which was the date of the run, so the run offered Monday 23 and Tuesday 24 November instead and said so first in its notes. The case's date is now in the past and will keep drawing this.

## What changed beyond the score

- Four cases gained a point. Case 1's paragraph has 210 words of prose against the 250 limit; the grader's earlier raw count, markup included, put it at 253 and failed it, and the reference run's paragraph at 435. Case 3 no longer derives a reading precision, case 4 kept every number to the abstract's own, and case 11 fits the rubric's 300 words with its markers in.
- Four runs used review passes, against six in the reference: the cold reader in case 4 (on the smaller model, 22,057 tokens), claim support and the cold reader in case 10, and the examiner in case 11. Case 1 judged its claim and quote pairs in the main run and stayed under 400 words, so it ran none and cost less than half its reference.
- Case 10 is the one case that cost more than its reference, and it holds 135,207 of the 349,980 extra tokens. It saved four preprints and searched the registries beyond the student's four papers, which found the two papers that narrow the dissertation's gap claim. That search is what the case rewards, but the run took 63 tool calls and 537 seconds, nearly three times the next longest run. It is the next place to cut.
- Case 13 found no catalogue record for a 7th edition of 2004 and left both real editions in the reference list under a marker, as the case expects.
