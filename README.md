# Writing skill

A skill for Claude that writes and edits prose people read (reports, dissertations, lab books, essays, lay summaries, emails, Teams messages, cover letters, personal statements and blog or LinkedIn posts) in a natural voice with UK English, changes tone on request, and verifies every citation against scholarly registries. It ships with a checker that flags the measurable signs of machine-written text.

## Layout

- `writing/`: the skill itself. `SKILL.md` routes each request to a register in `writing/registers/` and points to the shared rules (`tells.md`, `clarity.md`, `sources.md`, `sources-search.md`, `exemplars.md`), the tone dials (`voice.md`) and the fresh-context review passes (`review.md`).
- `writing/scripts/check.py`: the draft checker, standard library only.
- `writing/scripts/verify.py`: the source verifier, standard library only.
- `install.py`: installs the skill and builds the upload zip.
- `evals/`: the eval set, its input files, the grader, and the scripts that price runs from their transcripts, hide the arm from graders and compare runs with the reference.
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

Each input line is one source as the draft cites it: a key, a DOI or arXiv ID, the title, the authors' surnames, the year, optionally volume and pages, and the quoted passages each claim rests on. `writing/sources.md` gives the format. For each source it compares the cited fields with the registry record, looks for retractions and newer arXiv versions, and searches the abstract (or a saved full text) for each quote word for word. It prints the verification log as a Markdown table, a row as each source finishes. It exits 0 if every source is verified, 1 if any is not, 2 if the input cannot be read and 3 if the run stops on a fault. It needs network access, checks at most 50 sources per run and stops checking after five minutes. DOIs are looked up in Crossref, then DataCite when Crossref has no record; DOIs in neither are reported unverified. When a quote is not found, its row links to a free full text if OpenAlex or arXiv has one. Registry responses are cached for 24 hours in a file named after the sources file, such as `sources.cache.json`, beside it, so a rerun after editing a draft makes no repeat requests. `--refresh` ignores the cache and fetches again. Standard input keeps no cache. `--bib PATH` also writes a BibTeX file with an entry for each source whose cited fields all matched (status VERIFIED or CLAIM NOT CHECKED). Each entry is built from the registry record, not from the cited fields, so no reference is typed from memory. Crossref and DataCite text is escaped for LaTeX, arXiv titles and names are kept as the LaTeX they were submitted in, and the file is UTF-8. It is written after the checks, also when the run stops on a fault or at the time limit, and a line on standard error says how many sources were written and which were left out. A path in a folder that does not exist exits 2 before any request, and a write failure exits 3. `--draft PATH` appends a draft audit to the log: cite keys (LaTeX `\cite` commands or Pandoc `[@key]`) missing from the sources or attached to a source that failed, which are errors and make the exit code 1; cited sources whose claim was not checked, and numbers in a citing sentence that no quote of its sources contains, which are warnings; open gap markers; and sources never cited. An unreadable draft exits 2 before any request.

## Development

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run vulture writing/scripts install.py tests evals --min-confidence 80
```

The eval scripts that price, hide and compare runs need full branch coverage, and the locked dependencies are audited:

```
uv run coverage run --branch --source=evals -m pytest
uv run coverage report --show-missing --fail-under=100 --include=evals/spend.py,evals/compare.py,evals/blind.py
uv run coverage erase
uv export --format pylock.toml --no-emit-project -o <scratch>/pylock.toml && uv run pip-audit --locked <scratch>
```

### Evals

`evals/evals.json` holds thirteen cases in skill-creator's format, with their input files in `evals/files/`. Each case lists judgement expectations, which a grader reads the output against, and programmatic checks: checker errors, word limits (counted on the prose by `check.py --max-words`, as the skill counts them), hashtag limits, banned phrases, required gap markers, the share of one-sentence paragraphs, and whether every number in the output appears in the prompt or input files. Cases 10 to 13 are ones the base model finds hard: a literature review over four real papers with two misremembered details, a methods section marked against a rubric, a reflection that must match a sample of the student's writing, and a citation to a book with no DOI.

Each case runs in two arms in skill-creator's layout: `with_skill` follows the skill, and `without_skill` runs the same model with no skill, which shows what the skill adds and what it costs. Both arms run on each model under test, `opus` and `sonnet`. Run each case in a fresh subagent with its model set explicitly, with no access to `evals.json`, given this brief:

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

Reply with one line: done, or failed and why.
```

For the no-skill arm, the brief speaks of a writing task rather than a skill, drops "following the skill", and replaces the skill paragraph with "Skill: none. Do not use the Skill tool, and do not open anything under <repo>/writing/ or ~/.claude/skills/." Each case directory also holds its `eval_metadata.json`. A case whose spend has varied by more than 25% between runs runs twice per arm, the second time into `<arm>-2/`, and the median of the two counts.

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

Give an Opus subagent per case that case's blind folder and its expectations from `evals.json`, and nothing else; it writes each copy's grades to `grading.json` in that copy, as expectations with `text`, `passed` and `evidence`. Then map the grades back, score the programmatic checks and compare each model with the reference:

```
uv run python evals/blind.py reveal evals/workspace/iteration-5 --key <the key>
uv run python evals/grade.py evals/workspace/iteration-5/*/*/*_skill*
uv run python evals/compare.py evals/workspace/iteration-5 --model opus
uv run python evals/compare.py evals/workspace/iteration-5 --model sonnet
```

`reveal` writes nothing unless every copy is graded. The grader merges its results into each run's `grading.json`, keeping the judgement grades. `compare.py` prints each case's with-skill score and spend, subagents included, beside the model's section of `evals/reference.json`, which holds the reference with-skill run and the no-skill arm. It exits 1 when a case scores below its reference, when the total score does not beat the model's no-skill arm, when the extra spend over that arm on the cases `max_extra_spend` lists exceeds its budget, or, for a section that names a `rival`, when the total score is below the rival model's no-skill arm or the spend is not below it. It exits 2 when a run, a transcript or a price is missing or malformed. The no-skill arm is run once per model: rerun it and update the reference when the model or the prices change.

`evals/baseline.md` records the score of the skill before any change, `evals/after-upgrade.md` the score after the review passes, tones and new registers were added, `evals/after-efficiency.md` the score and cost after the work to cut tokens, and `evals/after-quality.md` the score and cost after the expectations for review passes and source search were added and the sources procedure was changed, which set the current reference.
