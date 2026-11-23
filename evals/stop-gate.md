# The draft gate on stopping

A Stop hook declared in the skill's frontmatter would rerun the last `check.py` or `verify.py --draft` command before a session ends, block the stop once if it failed, and let the skill drop its own rerun of the check after the review passes. The hook fires, but the most it could save is about 7% of a session's wall time, which three runs per arm cannot tell apart from noise. It was not built.

## Does a skill's Stop hook fire

Yes, in a headless session. A test skill in a scratch project's `.claude/skills/` declared a Stop hook that wrote its input to a file. `claude -p --model sonnet --allowedTools "Skill(stopspike)" -- "Run /stopspike"` (Claude Code 2.1.331) loaded the skill through the Skill tool and the hook fired on the stop, with `transcript_path`, `cwd` and `stop_hook_active: false` in its input. Without the allow rule, `claude -p` refused the Skill call and nothing fired.

The eval executors read `SKILL.md` as a file rather than through the Skill tool, so the hook would never fire in an eval run: no eval in the README's layout could credit it or catch a fault in it.

## What it could save

The gate replaces only the checker runs after a session's first, since the first is needed to find anything to fix. In iteration 10's `with_skill_medium` runs (Opus at medium, nine cases, three runs each), each such rerun was costed from the transcript entry before its tool call to the next model message after its result, so the model's turn to write the command is counted as well as the command itself. Medians per case:

| Case | Wall time | Rerun turns | Share |
|---|---|---|---|
| book-citation | 96 s | 0 s | 0.0% |
| cited-paragraph | 125 s | 8 s | 6.2% |
| literature-review | 333 s | 23 s | 7.0% |
| nonexistent-citation | 39 s | 0 s | 0.0% |
| novelty-claim | 120 s | 12 s | 9.9% |
| options-appraisal | 79 s | 5 s | 6.7% |
| recommendation-email | 49 s | 4 s | 7.3% |
| related-work-search | 149 s | 8 s | 5.6% |
| results-confound | 57 s | 9 s | 15.1% |
| Total | 1047 s | 69 s | 6.6% |

6.6% is an upper bound. Most reruns follow a failed check and confirm the fix; under the gate a failure found at the stop costs a blocked turn of about the same length, so only reruns after a clean check would go. The gate also adds its own run of the checker, and of the verifier on a cited draft, to every session. In 26 of the 27 runs the last check was already clean, so the gate would rarely have caught anything.

## Why it was dropped

On the two cases the phase would have measured, cited-paragraph and recommendation-email, the bound is 8 s of 125 s and 4 s of 49 s. From iteration 10 to iteration 11, book-citation's median time went from 96 s to 168 s although nothing it runs had changed. Six headless sessions per arm cannot resolve a gain under 7%, so the measurement would have cost about $12 without being able to keep the gate. A hook that parses shell commands from a transcript and reruns them is also the riskiest code the work would have added: a wrong parse blocks a stop or runs a command it should not.
