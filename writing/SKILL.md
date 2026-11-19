---
name: writing
description: Writes and edits prose that people read, in a natural human voice with UK English and no machine-writing giveaways. Use for reports, dissertations, project plans, papers, abstracts, lab books, essays, literature reviews, lay summaries, explainers for non-technical readers, emails and Teams or Slack messages, cover letters, personal statements, blog and LinkedIn posts, and for any request to draft, rewrite, tighten, humanise, rephrase or change the tone of such text. Covers finding and verifying every citation so no source, figure or result is invented. Not for code comments, docstrings, commit messages, pull request descriptions or READMEs.
---

# Writing

The writer is a final-year UK undergraduate in Physics with Computer Science. The aim is prose a careful expert would sign: clear to an outsider, exact for an examiner. The student declares AI use themselves, so never add notes on how the text was produced.

## Register

Read the matching register and its tier's files. If two fit, ask.

- `registers/report.md`: report, dissertation, plan, paper, abstract, literature review.
- `registers/labbook.md`: lab book, research diary, meeting record.
- `registers/essay.md`: essay, reflective piece.
- `registers/explainer.md`: lay summary, outreach, explainer.
- `registers/message.md`: email, Teams or Slack message.
- `registers/application.md`: cover letter, personal statement, application.
- `registers/post.md`: blog, LinkedIn or newsletter post.

A named tone ("warmer", "shorter", "more formal") also needs `voice.md`. Everywhere: UK spelling, no dashes as punctuation, no emoji, prose over lists.

## Effort

Each turn rereads the whole conversation, so read everything the tier names in one turn.

- **Light**, a message or an edit the request spells out: the register, unless the request names every change. Run only `scripts/check.py`, fixing only your own words.
- **Full**, text that draws on published work: the Standard files, `review.md`, `sources.md` and `sources-search.md`.
- **Standard**, anything else: the register, `clarity.md`, `tells.md`, and `review.md` for a rubric, an explainer or over 400 words.

Never open a script's source. After spawning a subagent, end the turn: it reports when done, so never poll or sleep. Revise with edits, not rewrites.

## Before drafting

1. A rubric, handbook, template, word limit or supervisor's instruction outranks this skill. Read it first.
2. Name the reader, the claim and the evidence, one sentence each.
3. Facts come only from the student's data, notes, code and results, or from verified sources, never from memory. A gap stays visible: `[DATA NEEDED: what]`, `[CITATION NEEDED: claim]`, or the markers `sources.md` defines.
4. A sample of the student's own writing sets the style: match its sentence length, "I" or "we", connectives and formality. Without one, read `exemplars.md` for work over about 800 words.

## Process

1. Ask for what is missing. Over about 800 words, agree an outline first: one claim sentence per paragraph.
2. Draft in the register.
3. Check the draft file with `scripts/check.py`, in one command, chaining `scripts/verify.py` for a cited draft as `sources.md` shows:

   ```
   python -I "<this skill's directory>/scripts/check.py" <draft> --format plain|markdown|latex --max-words <any limit set> --inputs <request saved to a file, notes and data>
   ```

   Fix every error and judge each warning as `tells.md` says.
4. Run the passes `review.md` gives and settle each finding by changing the text or showing it wrong, then rerun step 3's command.
5. Before delivering, look for what the checker cannot see:
   - a tone change that puts blame on a person;
   - a claim, skill or event the notes do not contain;
   - agreement with a value or model stated without its uncertainty;
   - a caveat of the source dropped from a summary;
   - one-sentence paragraphs in a post.
6. Deliver in the requested format, followed only by open markers, the verification log's location and judgement calls for the student.

## Editing the student's text

Keep their meaning, facts and voice, and change only what the rules require. Never add claims, sources or numbers; mark gaps instead. After a large change, name the main kinds of edit in one or two lines.
