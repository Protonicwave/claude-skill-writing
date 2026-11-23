---
name: writing
description: Writes and edits prose that people read, in a natural human voice with UK English and no machine-writing giveaways. Use for reports, dissertations, project plans, papers, abstracts, lab books, essays, literature reviews, lay summaries, explainers for non-technical readers, emails and Teams or Slack messages, cover letters, personal statements, blog and LinkedIn posts, and for any request to draft, rewrite, tighten, humanise, rephrase or change the tone of such text. Covers finding and verifying every citation so no source, figure or result is invented. Not for code comments, docstrings, commit messages, pull request descriptions or READMEs.
---

# Writing

The writer is a final-year UK undergraduate in Physics with Computer Science. The aim is prose a careful expert would sign: clear to an outsider, exact for an examiner. The student declares AI use themselves, so never add notes on how the text was produced.

## Register

Read the matching register and its tier's files. If two fit, take the reader's.

- `registers/decision.md`: recommendation, options appraisal or decision request, any form.
- `registers/report.md`: report, dissertation, plan, paper, abstract, literature review.
- `registers/labbook.md`: lab book, research diary, meeting record.
- `registers/essay.md`: essay, reflective piece.
- `registers/explainer.md`: lay summary, outreach, explainer.
- `registers/message.md`: email, Teams or Slack message.
- `registers/application.md`: cover letter, personal statement, application.
- `registers/post.md`: blog, LinkedIn or newsletter post.

A named tone ("warmer", "shorter") also needs `voice.md`. Everywhere: UK spelling, no dashes as punctuation, no emoji, prose over lists.

## Effort

Each turn rereads the conversation: read everything the tier names in one turn.

- **Light**, a message or an edit the request spells out: the register, unless the request names every change. Run only `scripts/check.py`, fixing only your own words.
- **Full**, text drawing on published work: the Standard files, `review.md`, `sources.md`, `sources-search.md` with `scripts/find_sources.py`, `scripts/gap_search.py`.
- **Standard**, anything else: the register, `clarity.md`, `tells.md`, and `review.md` for a rubric, an explainer or over 400 words.

Never open a script's source. After spawning a subagent, end the turn: it reports when done, so never poll or sleep. Revise with edits, not rewrites.

## Decisions

Decide every choice about the text and log it, including how each finding or forwarded comment is settled: a question costs the student a round trip, a logged choice one line to reverse.

- Never decide a fact only the student has, such as a result, date or name: mark it. Never send or publish.
- Never ask. When one draft cannot serve two readings (a lay summary or a technical abstract), write the likelier and name the other first in the notes.
- Settle reader, length, format, tone, deadline, scope: each is given, defaulted and logged, or marked.
- Before drafting, write three to six yes/no tests from the request, rubric and notes ("Does the opening give the value with its uncertainty?"), and give them to the examiner: specific tests catch what rereading misses.
- The notes end with a judgement log of choices the student might reverse, each with its reason and how to change it. A literal edit gets one or two sentences and no log.

## Before drafting

1. A rubric, handbook, template, word limit or supervisor's instruction outranks this skill. Read it first.
2. Name the claim and the evidence, one sentence each.
3. Facts come only from the student's data, notes, code and results, or from verified sources, never from memory. A gap stays visible: `[DATA NEEDED: what]`, `[CITATION NEEDED: claim]`, or the markers `sources.md` defines.
4. A sample of the student's own writing sets the style: match its sentence length, "I" or "we", connectives and formality. Without one, read `exemplars.md` for work over 800 words.

## Process

1. Over 800 words, outline first: one claim sentence per paragraph, shown in the notes.
2. Draft in the register.
3. Check the draft file with `scripts/check.py`, in one command, chaining `scripts/verify.py` for a cited draft as `sources.md` shows:

   ```
   python -I "<this skill's directory>/scripts/check.py" <draft> --format plain|markdown|latex --max-words <any limit set> --inputs <request saved to a file, notes and data>
   ```

   Fix every error and judge each warning as `tells.md` says. Stop after three runs and list what is left in the notes.
4. If the tier read `review.md`, run its passes, settle each finding as it says, then rerun step 3's command.
5. Before delivering, check each test, and that nothing the notes lack was added and no caveat dropped.
6. Deliver in the requested format, followed only by open markers, the logs' locations, what other files send to the notes, and the judgement log.

## Editing the student's text

Keep their meaning, facts and voice, and change only what the rules require. Never add claims, sources or numbers; mark gaps instead. After a large change, name the main kinds of edit in one or two lines.
