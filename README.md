# Writing skill

A skill for Claude that writes and edits prose people read (reports, dissertations, lab books, essays, lay summaries, emails, Teams messages, cover letters, personal statements and blog or LinkedIn posts) in a natural voice with UK English, changes tone on request, and verifies every citation against scholarly registries. It ships with a checker that flags the measurable signs of machine-written text.

## Layout

- `writing/`: the skill itself. `SKILL.md` routes each request to a register in `writing/registers/` and points to the shared rules (`tells.md`, `clarity.md`, `sources.md`, `sources-search.md`, `exemplars.md`), the tone dials (`voice.md`) and the fresh-context review passes (`review.md`).
- `writing/scripts/check.py`: the draft checker, standard library only.
- `writing/scripts/verify.py`: the source verifier, standard library only.
- `writing/scripts/gap_search.py`: the search for published work that closes a stated gap, built on the verifier.
- `install.py`: installs the skill and builds the upload zip.
- `evals/`: the eval set, its input files, the grader, and the scripts that price runs from their transcripts, hide the arm from graders, compare runs with the reference and compare two arms on time.
- `tests/`: checker rules, verifier, grader, eval scripts, skill structure and installer.

## Install

Requires Python 3.12 or later.

```
python install.py
```

This copies `writing/` to `~/.claude/skills/writing`, where Claude Code picks it up in every project, and writes `dist/writing.zip`. Upload the zip in claude.ai under Settings, Capabilities, Skills to use it in chats. Run the command again after any change so both copies stay identical.

Options: `--skills-dir` and `--dist` change the destinations; `--source` installs from another folder. The installer refuses to replace a `writing` folder that holds a different skill.

## Use

Ask for the writing in plain words ("draft the discussion for my report", "rephrase this for Teams") and the skill loads itself, or call it with `/writing`.

The checker also runs on its own:

```
python writing/scripts/check.py draft.tex
python writing/scripts/check.py notes.md --format markdown
python writing/scripts/check.py - < message.txt
python writing/scripts/check.py report.tex --outline
python writing/scripts/check.py summary.md --max-words 250
python writing/scripts/check.py summary.md --inputs notes.md results.csv
```

The format follows the extension (`.md`, `.tex`, anything else plain) unless `--format` is given. It exits 1 if any error is found, 2 if the draft cannot be read, and 0 otherwise. Errors (dashes used as punctuation, emoji, chatbot phrases) must be fixed. Warnings need judgement: physics uses some flagged words, such as potential or robust, in their technical sense. `--max-words N` adds an error when the prose runs past N words, counting the text without markup, maths, code or link targets, on the line where the limit is passed. `--inputs FILE ...`, placed after the draft, adds a warning for each number in the draft, maths included, that none of the files contains, so a number with no source shows before anyone reads the text. Cite keys, labels, file names and options in LaTeX commands, link targets and URLs are skipped, as are ISO dates and integers up to 10, and `1,234` matches `1234`. A derived number is legitimate: say how it was derived. An input that cannot be read exits 2 before any check. `--outline` prints the first sentence of each body paragraph with its line number and checks nothing, so the argument can be read in order.

The verifier checks cited papers against Crossref, DataCite, OpenAlex and arXiv:

```
python writing/scripts/verify.py sources.jsonl > references-log.md
python writing/scripts/verify.py - < sources.jsonl
python writing/scripts/verify.py --refresh sources.jsonl
python writing/scripts/verify.py --bib references.bib sources.jsonl
python writing/scripts/verify.py --draft report.tex sources.jsonl
```

Each input line is one source as the draft cites it: a key, a DOI or arXiv ID, the title, the authors' surnames, the year, optionally volume and pages, and the quoted passages each claim rests on. `writing/sources.md` gives the format. For each source it compares the cited fields with the registry record, looks for retractions and newer arXiv versions, and searches the abstract (or a saved full text) for each quote word for word. It checks up to four sources at once, keeping to each registry's published limits (Crossref one request at a time and five a second, OpenAlex ten a second, arXiv one every three seconds), and prints the verification log as a Markdown table, a row as each source finishes, in input order. It exits 0 if every source is verified, 1 if any is not, 2 if the input cannot be read and 3 if the run stops on a fault. It needs network access, checks at most 50 sources per run and stops checking after five minutes. OpenAlex meters anonymous use by a daily credit budget, about 100 searches a day; set an OpenAlex API key in the `OPENALEX_API_KEY` environment variable to raise it (about 1,000 searches a day for a free key). The key is sent only to OpenAlex and is never written to the cache, the logs or error messages. A registry that asks for a wait of an hour or more has spent its budget for the day, and its requests fail at once instead of retrying. DOIs are looked up in Crossref, then DataCite when Crossref has no record; DOIs in neither are reported unverified. When a quote is not found, its row links to a free full text if OpenAlex or arXiv has one. Registry responses are cached for 24 hours in a file named after the sources file, such as `sources.cache.json`, beside it, so a rerun after editing a draft makes no repeat requests. `--refresh` ignores the cache and fetches again. Standard input keeps no cache. `--bib PATH` also writes a BibTeX file with an entry for each source whose cited fields all matched (status VERIFIED or CLAIM NOT CHECKED). Each entry is built from the registry record, not from the cited fields, so no reference is typed from memory. Crossref and DataCite text is escaped for LaTeX, arXiv titles and names are kept as the LaTeX they were submitted in, and the file is UTF-8. It is written after the checks, also when the run stops on a fault or at the time limit, and a line on standard error says how many sources were written and which were left out. A path in a folder that does not exist exits 2 before any request, and a write failure exits 3. `--draft PATH` appends a draft audit to the log: cite keys (LaTeX `\cite` commands or Pandoc `[@key]`) missing from the sources or attached to a source that failed, which are errors and make the exit code 1; cited sources whose claim was not checked, and numbers in a citing sentence that no quote of its sources contains, which are warnings; open gap markers; and sources never cited. An unreadable draft exits 2 before any request.

The gap search looks for published work that already does what a gap claim says has not been done:

```
python writing/scripts/gap_search.py --log notes/gap-search.md "neural network sampler Ising model" "generative model Monte Carlo spin systems" "self-learning Monte Carlo"
```

It takes exactly three queries of two to eight words and sends each once to the OpenAlex search and once to the arXiv search, where every word must match. It keeps at most five hits from each answer and lists a work found more than once, or held by both registries, once. Each hit prints on one line with its identifiers, year, title, the first 300 characters of its abstract and the requests that found it; the output stops at 12,000 characters, and the rest are only in the log. The log is Markdown: the date, the queries, each request's URL and outcome, and every hit. Responses share the verifier's 24-hour cache, `sources.cache.json` beside the log. No request starts after 120 seconds. It exits 0 when every request was answered, 1 when a registry was unavailable, sent a malformed answer or a request was not started in time (the other hits still print), 2 for invalid queries or a log folder that does not exist, and 3 when the log cannot be written.

## Development

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run vulture writing/scripts install.py tests evals --min-confidence 80
```

The eval scripts that price, hide, compare and time runs, and the gap search, need full branch coverage, and the locked dependencies are audited:

```
uv run coverage run --branch --source=evals,writing/scripts -m pytest
uv run coverage report --show-missing --fail-under=100 --include=evals/spend.py,evals/compare.py,evals/blind.py,evals/speed.py,evals/verify_timing.py,writing/scripts/gap_search.py
uv run coverage erase
uv export --format pylock.toml --no-emit-project -o <scratch>/pylock.toml && uv run pip-audit --locked <scratch>
```

### Evals

`evals/evals.json` holds twenty-two cases in skill-creator's format, with their input files in `evals/files/`. Each case lists judgement expectations, which a grader reads the output against, and programmatic checks: checker errors, word limits (counted on the prose by `check.py --max-words`, as the skill counts them), hashtag limits, banned phrases, required gap markers, the share of one-sentence paragraphs, and whether every number in the output appears in the prompt or input files. Cases 10 to 13 are ones the base model finds hard: a literature review over four real papers with two misremembered details, a methods section marked against a rubric, a reflection that must match a sample of the student's writing, and a citation to a book with no DOI. Cases 14 to 17 score the choices the skill makes for itself: reviewer comments of which one is wrong, a request that leaves its length unstated and one figure missing, an edit of one word in two places whose spend is what counts, and a rubric that overrides the skill's own style. Cases 18 to 20 score analysis and decisions the student asks for: a recommendation that one constraint in the notes rules out, results whose difference coincides with a recalibration, and an options appraisal that a handbook rule narrows. Cases 21 and 22 score breadth of search, where deep research is expected to be strong: a related-work paragraph from a project description with no papers, and an aims and novelty paragraph whose notes claim a first that published work already contradicts.

Each case runs in two arms in skill-creator's layout: `with_skill` follows the skill, and `without_skill` runs the same model with no skill, which shows what the skill adds and what it costs. Both arms run on each model under test, `opus` and `sonnet`. Run each case in a fresh subagent with its model and effort set explicitly (`effort: medium` for Opus, which `evals/effort.md` chose), with no access to `evals.json`, given this brief:

```
You are running one test case of a writing skill. Act on the request below exactly as you would for a real user, following the skill.

Skill: read <repo>/writing/SKILL.md first and follow it, reading the other skill files it points to as you need them. Use this copy, not any installed copy. Its scripts are in <repo>/writing/scripts/.

The user's request, in their words:
"<prompt>"

The user's files: <absolute paths, or none>

Output directory: <repo>/evals/workspace/iteration-<N>/<model>/<eval name>/<arm>/outputs/
- Save the text you would deliver, exactly as delivered, to outputs/deliverable.md.
- Save what you would tell the user after the text (open markers, judgement calls, where logs are) to outputs/notes.md.
- Save every other file you create (sources file, verification log, saved pages, drafts) in outputs/.

There is no user to answer questions. Where the skill says to ask, take the most reasonable reading and record the question in notes.md. Do not open anything else under <repo>/evals/ apart from the user's files above.

Reply with one line: done, or failed and why. Also say whether any subagent you tried to start was refused.
```

For the no-skill arm, the brief speaks of a writing task rather than a skill, drops "following the skill", and replaces the skill paragraph with "Skill: none. Do not use the Skill tool, and do not open anything under <repo>/writing/ or ~/.claude/skills/." Each case directory also holds its `eval_metadata.json`. A case whose spend has varied by more than 25% between runs runs twice per arm, the second time into `<arm>-2/`, and the median of the two counts.

The research cases (`cited-paragraph`, `nonexistent-citation`, `literature-review`, `book-citation`, `related-work-search` and `novelty-claim`) also run a `deep_research` arm, `deep_research-2/` and so on for repeats, in the same iteration and layout. It runs the same model with Anthropic's deep-research skill in place of this one, and `compare.py --against deep_research` measures the skill against it. Run each in a fresh subagent with its model set explicitly, given this brief:

```
You are running one test case of a research and writing comparison. Act on the request below exactly as you would for a real user.

Skill: use the deep-research skill (invoke it with the Skill tool, skill name anthropic-skills:deep-research) for the research. Do not use the writing skill, and do not open anything under <repo>/writing/ or ~/.claude/skills/writing. Do the research the deep-research skill calls for, then write the deliverable the user asked for.

The user's request, in their words:
"<prompt>"

The user's files: <absolute paths, or none>

Output directory: <repo>/evals/workspace/iteration-<N>/<model>/<eval name>/deep_research/outputs/
- Save the text you would deliver, exactly as delivered, to outputs/deliverable.md.
- Save what you would tell the user after the text (open markers, judgement calls, where logs are) to outputs/notes.md.
- Save every other file you create (sources, research notes, saved pages, drafts) in outputs/.

There is no user to answer questions. Where you would ask, take the most reasonable reading and record the question in notes.md. Do not open anything else under <repo>/evals/ apart from the user's files above.

Reply with one line: done, or failed and why. Also say whether you could spawn subagents for the research.
```

Capture, hide and grade these runs as the others: `blind.py` hides `deep_research` runs under ids like any other, and the grade glob becomes `*/*/*_skill* */*/deep_research*`. Then:

```
uv run python evals/compare.py evals/workspace/iteration-9 --model opus --against deep_research
uv run python evals/compare.py evals/workspace/iteration-9 --model sonnet --against deep_research
```

For each case in the model's `deep_research` entry in `evals/reference.json`, it prints the median score and spend of the `with_skill` runs beside those of the `deep_research` runs, and exits 1 when the skill scores below deep research or spends the same or more. It also prints the gap search's extra spend beside its budget: the skill's median spend on the entry's `gap_search_budget` case, less `baseline_usd` (the figure before the gap search existed), may be at most `max_share_of_rival` of deep research's median spend on that case, or the run exits 1. Spend leaves out a web search's own fee, so deep research's figure is understated.

When a run finishes, copy its transcript, and those of every subagent it spawned, into its run directory. The launch result gives the run's agent id, and Claude Code keeps the transcripts in `~/.claude/projects/<project>/<session>/subagents/`:

```
uv run python evals/spend.py capture <agent id> evals/workspace/iteration-5/opus/data-gap/with_skill --from <subagents folder>
uv run python evals/spend.py price evals/workspace/iteration-5/opus/*/with_skill
```

`price` prints each run's spend in US dollars at the list prices in `evals/reference.json`, dated when they were read, with each message priced once at its own model's rates and cache reads and writes priced as such. Requests a tool makes outside the transcript, such as a web search's own model call, are not counted.

Grade the judgement expectations blind, so the grader knows neither the arm nor the model. `hide` copies every run's outputs to `blind/<case>/<random id>/` and writes the key to a path outside the iteration:

```
uv run python evals/blind.py hide evals/workspace/iteration-5 --key <path outside the iteration>
```

Give an Opus subagent per case that case's blind folder, its prompt and expectations from `evals.json` and its input files, and nothing else; it writes each copy's grades to `grading.json` in that copy, as expectations with `text`, `passed` and `evidence`. Then map the grades back, score the programmatic checks and compare each model with the reference:

```
uv run python evals/blind.py reveal evals/workspace/iteration-5 --key <the key>
uv run python evals/grade.py evals/workspace/iteration-5/*/*/*_skill* evals/workspace/iteration-5/*/*/deep_research*
uv run python evals/compare.py evals/workspace/iteration-5 --model opus
uv run python evals/compare.py evals/workspace/iteration-5 --model sonnet
```

`reveal` writes nothing unless every copy is graded. The grader merges its results into each run's `grading.json`, keeping the judgement grades. `compare.py` prints each case's with-skill score and spend, subagents included, beside the model's section of `evals/reference.json`, which holds the reference with-skill run and the no-skill arm. It exits 1 when a case scores below its reference, when the total score does not beat the model's no-skill arm, when the extra spend over that arm on the cases `max_extra_spend` lists exceeds its budget, or, for a section that names a `rival`, when the total score is below the rival model's no-skill arm or the spend is not below it. It exits 2 when a run, a transcript or a price is missing or malformed. The no-skill arm is run once per model: rerun it and update the reference when the model or the prices change.

A skill arm that tries a variant of the skill or its settings is named for it, such as `with_skill_medium`, and is hidden, graded and compared like `with_skill`. To compare two arms on score, spend and wall time, case by case, give the arm under test, the baseline arm and the most wall time the arm may take as a share of the baseline's:

```
uv run python evals/speed.py evals/workspace/iteration-10 --model opus --arm with_skill_medium --against with_skill_high --max-seconds-ratio 0.75
uv run python evals/speed.py evals/workspace/iteration-11 --model opus --arm with_skill_search --against with_skill_medium --baseline-iteration evals/workspace/iteration-10 --case literature-review --case novelty-claim
```

A run's wall time is the span from the earliest to the latest timestamp in its transcript and its subagents' transcripts, and a case's figure is the median over the arm's repeats. The command prints each case's score, spend and time beside the baseline's, with the summed time ratio beside its budget, and exits 1 when the time is over the ratio, the summed spend is higher or any case scores lower, and 2 when a run, transcript, timestamp or grade is missing or a case has runs of one arm only. `--case NAME`, repeated, limits the comparison to the cases named, so an arm run on some cases can be set against a baseline that ran more. Launch both arms in one batch so machine load affects them alike.

The verifier's own speed is timed on the fifteen sources in `evals/verify_timing.jsonl`, three cold runs in fresh processes:

```
uv run python evals/verify_timing.py
```

It prints each run's seconds, the median and the budget, 0.7 of the 7.4 s median measured when sources were fetched one at a time, and exits 1 when the median is over it and 2 when a run fails to verify every source. `--max-seconds` and `--runs` change the budget and the number of runs. Registry latency varies by hour, so compare figures taken minutes apart.

`evals/baseline.md` records the score of the skill before any change, `evals/after-upgrade.md` the score after the review passes, tones and new registers were added, `evals/after-efficiency.md` the score and cost after the work to cut tokens, and `evals/after-quality.md` the score and cost after the expectations for review passes and source search were added and the sources procedure was changed, which set the current reference. `evals/before-judgement.md` and `evals/after-judgement.md` record all four arms before the judgement changes and the with-skill arms after them, with the spend budgets and the rerun that followed a change to the notes rule. `evals/after-gap-search.md` records the skill against deep research on the six research cases, every run's score and spend, after the gap search was added. `evals/effort.md` records the skill on Opus at medium and at high effort on the research and decision cases, with wall time, and why medium was chosen. `evals/batched-search.md` records the batched source search against the per-claim search it would have replaced, and why it was reverted.
