# Writing skill

A skill for Claude that writes and edits prose people read (reports, dissertations, lab books, essays, lay summaries, emails, Teams messages, cover letters, personal statements and blog or LinkedIn posts) in a natural voice with UK English, changes tone on request, and verifies every citation against scholarly registries. It ships with a checker that flags the measurable signs of machine-written text.

## Layout

- `writing/`: the skill itself. `SKILL.md` routes each request to a register in `writing/registers/` and points to the shared rules (`tells.md`, `clarity.md`, `sources.md`, `exemplars.md`), the tone dials (`voice.md`) and the fresh-context review passes (`review.md`).
- `writing/scripts/check.py`: the draft checker, standard library only.
- `writing/scripts/verify.py`: the source verifier, standard library only.
- `install.py`: installs the skill and builds the upload zip.
- `evals/`: the eval set, its input files and the grader.
- `tests/`: checker rules, verifier, grader, skill structure and installer.

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
```

The format follows the extension (`.md`, `.tex`, anything else plain) unless `--format` is given. It exits 1 if any error is found, 2 if the draft cannot be read, and 0 otherwise. Errors (dashes used as punctuation, emoji, chatbot phrases) must be fixed. Warnings need judgement: physics uses some flagged words, such as potential or robust, in their technical sense. `--outline` prints the first sentence of each body paragraph with its line number and checks nothing, so the argument can be read in order.

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

### Evals

`evals/evals.json` holds nine cases in skill-creator's format, with their input files in `evals/files/`. Each case lists judgement expectations, which a grader reads the output against, and programmatic checks: checker errors, word and hashtag limits, banned phrases, required gap markers, the share of one-sentence paragraphs, and whether every number in the output appears in the prompt or input files.

Run each case with skill-creator, saving the delivered text as `outputs/deliverable.md` in a run directory under `evals/workspace/`, then score the programmatic checks:

```
uv run python evals/grade.py evals/workspace/iteration-1/*/with_skill
```

The grader merges its results into each run's `grading.json`, keeping any expectations a grader has already written there. `evals/baseline.md` records the score of the skill before any change, with the brief each run was given, so a later run can be made the same way and compared case by case.
