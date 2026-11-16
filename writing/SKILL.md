---
name: writing
description: Writes and edits prose that people read, in a natural human voice with UK English and no machine-writing giveaways. Use for reports, dissertations, project plans, papers, abstracts, lab books, essays, literature reviews, lay summaries, explainers for non-technical readers, emails and Teams or Slack messages, cover letters, personal statements, blog and LinkedIn posts, and for any request to draft, rewrite, tighten, humanise, rephrase or change the tone of such text. Covers finding and verifying every citation so no source, figure or result is invented. Not for code comments, docstrings, commit messages, pull request descriptions or READMEs.
---

# Writing

The writer is a final-year UK undergraduate in Physics with Computer Science. The aim is prose a careful expert would sign: clear to an outsider, exact for an examiner. The student declares AI use themselves, so never add notes on how the text was produced.

## Register

Read the matching register first; it names any other file it needs. If two fit, ask.

| Request | File |
|---|---|
| Report, dissertation, plan, paper, abstract, literature review | `registers/report.md` |
| Lab book, research diary, meeting record | `registers/labbook.md` |
| Essay, reflective piece | `registers/essay.md` |
| Lay summary, outreach, explainer | `registers/explainer.md` |
| Email, Teams or Slack message | `registers/message.md` |
| Cover letter, personal statement, application | `registers/application.md` |
| Blog, LinkedIn or newsletter post | `registers/post.md` |

A named tone ("warmer", "shorter", "more formal") also needs `voice.md`. No tone changes a fact, a request or the size of a hedge.

## Before drafting

1. A rubric, handbook, template, word limit or supervisor's instruction outranks this skill. Read it first.
2. Name the reader, the claim and the evidence, one sentence each.
3. Facts come only from the student's data, notes, code and results, or from verified sources, never from memory. A gap stays visible: `[DATA NEEDED: what]`, `[CITATION NEEDED: claim]`, or the markers `sources.md` defines.
4. When the text cites, quotes or leans on published work, read `sources.md`, and `sources-search.md` to find new sources. A cited draft always has a verification log.
5. A sample of the student's own writing sets the style: match its sentence length, "I" or "we", connectives and formality. Without one, read `exemplars.md` for work over about 800 words.

## Voice

- Open on the specific problem, object or result, never on the field's importance.
- One term per concept, glossed in plain words at first use and never swapped for a synonym (`clarity.md`).
- Numbers over adjectives. Every claim answers "how do you know?".
- Hedge once, where the uncertainty is, with its size or reason.
- Report what failed and what could invalidate the result.
- Sentence length follows the content: no uniform rhythm, no one-line punches.
- End a paragraph on its newest point, and a report on its limitation or open question.
- UK spelling; no dashes as punctuation, emoji, bold in prose, pleasantries or empty signposting; sentence-case headings; prose over lists.

## Process

1. Ask for what is missing. Over about 800 words, agree an outline first: one claim sentence per paragraph.
2. Draft in the register.
3. Check the draft file with `scripts/check.py`, in one command:

   ```
   python -I "<this skill's directory>/scripts/check.py" <draft> --format plain|markdown|latex --max-words <limit> --inputs <notes and data files>
   ```

   `--max-words` takes any limit the request or rubric sets; `--inputs` takes every file the facts came from, with the request saved as one. A cited draft chains `scripts/verify.py` on, as `sources.md` shows. Fix every error. Judge each warning: an unknown number is derived and said so, or it goes; a flagged word in its technical sense stays. If it warns, `tells.md` says what to write instead. Over a few paragraphs, run `--outline` alone: it prints each first sentence, which together should state the argument. Without code execution, apply `tells.md` by hand.
4. If the draft cites, has a rubric, is an explainer or runs over 400 words, run the passes `review.md` gives and settle each finding by changing the text or showing it wrong. Then rerun step 3's command.
5. Before delivering, look for what the checker cannot see:
   - a tone change that puts blame on a person;
   - a claim, skill or event the notes do not contain;
   - agreement with a value or model stated without its uncertainty;
   - a caveat of the source dropped from a summary;
   - one-sentence paragraphs in a post.
6. Deliver in the requested format, followed only by open markers, the verification log's location and judgement calls for the student.

## Editing the student's text

Keep their meaning, facts and voice, and change only what the rules require. Never add claims, sources or numbers; mark gaps instead. After a large change, name the main kinds of edit in one or two lines.

