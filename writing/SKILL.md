---
name: writing
description: Writes and edits prose that people read, in a natural human voice with UK English and no machine-writing giveaways. Use for reports, dissertations, project plans, papers, abstracts, lab books, essays, literature reviews, lay summaries, explainers for non-technical readers, emails and Teams or Slack messages, and for any request to draft, rewrite, tighten, humanise or rephrase such text. Covers finding and verifying every citation so no source, figure or result is invented. Not for code comments, docstrings, commit messages, pull request descriptions or READMEs.
---

# Writing

The writer is a final-year UK undergraduate in Physics with Computer Science. The aim is prose a careful expert would sign: clear to a reader outside the field, exact enough for an examiner inside it, and free of the habits that make text read as machine-made. The student declares AI use in their own words. Never add AI statements, disclaimers or notes about how the text was produced to the text itself.

Good writing is the goal, not disguise. Most giveaways are symptoms of one fault: text written without a specific claim to make. The fix for nearly all of them is to say the specific thing.

## Pick the register

Read the matching file in `registers/` before drafting. Choose from the request and the destination; if both readings are plausible, ask one question.

| Request | File |
|---|---|
| Final report, dissertation, project plan, paper, abstract, lab report, progress report, literature review | `registers/report.md` |
| Lab book entries, research diary, meeting notes kept as a record | `registers/labbook.md` |
| Essay, reflective piece, argued answer to a question | `registers/essay.md` |
| Lay summary, outreach piece, explainer for a reader outside physics or computing | `registers/explainer.md` |
| Email, Teams or Slack post, message to a supervisor, teammate or client | `registers/message.md` |

When the request names a tone ("warmer", "more formal", "less blunt", "shorter", "more confident"), read `voice.md` as well. Tone is five dials set on top of the register, and no tone changes a fact, a request or a hedge's size.

## Before drafting

1. **Find the local rules.** A rubric, module handbook, template, word limit or supervisor's instruction outranks this skill. If the working folder holds one, read it first. The PHC903 report rubric, for example, rewards "publishable quality" and "full compliance with journal style", which settles the register.
2. **Name the reader, the claim and the evidence.** One sentence each. If the claim cannot be stated in a sentence, the draft is not ready to start.
3. **Take facts only from what exists.** Numbers, results, dates, names and quotations come from the student's data, notes, code and results, or from sources verified under `sources.md`. Nothing is filled in from memory. A gap stays visible as a marker:
   - `[DATA NEEDED: what]` for a number or result the student has not supplied;
   - `[CITATION NEEDED: claim]` for a claim with no source yet;
   - `[UNVERIFIED: source as given]` and `[CLAIM NOT CHECKED: reason]` as `sources.md` defines them.
4. **Sources.** Whenever the text cites, quotes or leans on published work, read `sources.md` and follow it: it says how to find sources on a fixed budget and how to check them with `scripts/verify.py`. No reference is ever written from memory.
5. **Match the student's own voice when there is a sample.** If the student supplies writing of their own, it outranks `exemplars.md`: match its sentence length, its use of "I" and "we", its connectives and its level of formality. Without a sample, calibrate on `exemplars.md`.

## The voice

These are the rules that matter most. `tells.md` and `clarity.md` give the evidence and the detail.

1. **Open on the specific problem**, the object or the result, never on how important the field is.
2. **One term per concept.** Introduce a technical term at the end of a sentence that starts from something the reader already knows, gloss it in plain words in the same sentence, then use exactly that term every time. Never swap in a synonym for variety. Keep the precise word; explaining it is clarity, removing it is vagueness.
3. **Put the action in the verb** ("we measured", not "a measurement was performed"). Bring the verb in soon after the subject. Known information first in a sentence, new information last.
4. **Numbers over adjectives.** "Above 1.6 W" rather than "at high power". Every claim answers "how do you know?" with data, a derivation or a citation.
5. **Let sentence length follow the content.** A long sentence for a qualified mechanism, a short one for the verdict. Uniform rhythm is the strongest measured sign of machine prose; artificial one-line punches are the second.
6. **Hedge once, where the uncertainty is, and give its size or reason.** "Consistent with the model within 1σ" stays; "may potentially suggest" goes.
7. **Report what failed** and what could invalidate the result, with numbers.
8. **Link ideas by their logic**: because, so, but, which means, for example. Not "Furthermore", "Moreover" or "Additionally" as padding.
9. **End on the newest important point.** A paragraph does not restate itself; a report ends on its limitation or open question, not a summary flourish.
10. **Analogies earn their place or go.** Use one only if it is exact, shorter than the literal explanation, and you can say where it breaks. State the break. Then return to the precise statement.
11. **Punctuation.** No em dashes, no en dashes as punctuation and no spaced hyphen standing in for a dash. Use the mark the logic needs: a comma for a light aside, brackets for a true parenthesis, a colon for an expansion, a full stop for a new claim. Do not turn every former dash into a colon; that becomes its own pattern.
12. **UK English**: analyse, optimise, modelling, colour, centre, behaviour, programme for a plan (program for software). Quotations keep their original spelling.
13. **Formatting serves the destination.** Prose paragraphs by default; a list only for discrete parallel items such as apparatus or steps. No bold in running prose, sentence-case headings, and output in the target format (LaTeX, Word-ready text or Markdown).
14. **No chatbot residue and no empty signposting.** No pleasantries, offers of further help or announcements of what a section will explore (`tells.md` lists them). A sentence that orients the reader must carry content: "Section 3 shows the fit fails above 300 K."

## Process

1. Gather as above. Ask for what is missing rather than guess.
2. For anything over about 800 words, agree an outline first: each paragraph as one sentence stating its claim.
3. Draft in the chosen register.
4. Revise against `tells.md` and `clarity.md`. Read each paragraph as the named reader would.
5. Run the checker on the draft. In Claude Code, save the draft to a file (or use the file being written) and run:

   ```
   python "<this skill's directory>/scripts/check.py" <draft> [--format plain|markdown|latex]
   ```

   It reads `-` as standard input. Fix every error. Judge every warning: a listed word used in its technical sense (potential energy, robust estimator) stays; decoration goes. Where code execution is unavailable, apply `tells.md` by hand.
6. Have the draft read with fresh eyes, as `review.md` says: whether each quote supports its claim as worded, whether the named reader can follow it, and, when a rubric exists, how an examiner would mark it. Settle every finding by changing the text or showing the finding wrong.
7. Deliver the text in the requested format. After it, briefly and only if they exist: open markers, where the verification log is, and any judgement call the student should check. No summary of what was written.

## Editing the student's own text

When asked to rewrite, tighten or "make it sound more human", keep the student's meaning, facts and voice. Change what the rules require and nothing else. Never add claims, sources or numbers that were not there; mark gaps instead. If the change is large, list the main kinds of edit in one or two lines after the text.

## Files

- `tells.md`: the catalogue of giveaways, each with what to write instead.
- `clarity.md`: defining terms, explaining equations, ordering information, analogies, precision.
- `sources.md`: finding sources on a budget, verifying them, gap markers, the verification log, citation styles.
- `exemplars.md`: short passages from admired human writers and what each one does.
- `review.md`: the fresh-context passes for claim support, a cold reader and an examiner.
- `voice.md`: tone on request as five dials, their defaults for each register, and what no tone may change.
- `registers/`: one file per kind of writing.
- `scripts/check.py`: the draft checker.
- `scripts/verify.py`: checks references and quoted passages against the registries.
