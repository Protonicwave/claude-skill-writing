# Report register

Final reports, dissertations, project plans, papers, abstracts, lab reports, progress reports and literature reviews.

## The target

A well-written journal paper. The PHC903 final report rubric gives 20% to writing and asks at the top band for "publishable quality" and "full compliance with journal style"; the 75% band asks the writer to be "eloquent in the expression of their subject" and to "convey ideas in a transparent, clear fashion". The analysis criterion (40%) asks for results set in context "of appropriate and published material, showing how conclusions are supported by the data". Write to that.

Narrative belongs in the introduction and the discussion, where the report tells the story of a question: what was unknown, why it was hard, what was tried, what was found. Methods and results stay plain, because a reader uses them to check the work, not to enjoy it.

If a rubric, handbook or template is in the working folder, it overrides this file. Check word or page limits before drafting and write to them.

## Voice

- Use "we", or the passive for procedure, unless the department says otherwise. Use "I" only where the department allows it for a single author, and then only for the writer's own judgements.
- Past tense for what was done and found; present tense for what is generally true and for what the report shows ("Figure 3 shows").
- Confidence comes from evidence. State results flatly with their uncertainty; hedge once, where the uncertainty is.

## Section by section

**Abstract.** Stands alone. The problem in one sentence, the method in one, the main results as numbers with uncertainties and a comparison to the expected value, and what they mean. No citations, no undefined abbreviations, no "this report will".

**Introduction.** Open on the specific problem, not on the field's importance. Then the funnel: the problem; what is known, told as a short history with names, dates and citations; the gap; the aim and how the report meets it. Each paragraph opens by naming the next constraint or step, so the introduction reads as a chain of reasons. A closing sentence on how the report is organised is conventional and expected.

**Theory or background.** Only what the reader needs to follow the results. Every equation introduced, displayed, numbered, its symbols defined in words with units, and read physically afterwards (`clarity.md`). Refer back to equations by name and number.

**Method.** Enough for a competent reader to repeat the work. Justify every assumption, approximation and choice of parameter, and state the uncertainty in each measured quantity: the rubric rewards "evident justification of any assumptions, approximations and uncertainties". Name the method (least-squares fit, Metropolis sampling), not the library call. For simulation work, state the model, its parameters, the random seeds or ensemble size, and how convergence was checked.

**Results.** Report, do not interpret. Every number with its uncertainty and units, in the form (1.42 ± 0.01) × 10⁻¹. Each figure referred to in the text before it appears, with the one thing the reader should see in it.

**Discussion.** The most important section and the most narrative. Interpret each result against the underlying physics and the published literature: agreement within uncertainty, or disagreement and its likely cause, quantified. Give the details that could throw doubt on the interpretation. Name the limitations by size, not as a ritual ("human error" is never an explanation). Say what the result means for the field and what the next measurement would be.

**Conclusion.** Link the results back to the aims in the introduction. No new concepts, no new results. End on the open question or the limitation that matters most, not on a restatement.

**Project plan.** Aims stated as checkable outcomes, the method for each, the risks with their mitigations, and a timeline whose tasks match the aims one for one. Write it as a plan the reader could hold the student to.

**Literature review.** Organised by question or by approach, never as a list of papers one after another. Each paragraph makes a claim about the field and cites the papers that support or contest it. Every source verified under `sources.md`.

## Figures and tables

- A caption stands alone: what is plotted, under what conditions, and the point to take from it. An illustrative example, numbers invented for the shape only: "Ground-state probability against anneal time for N = 16 spins; the nonlinear schedule (circles) reaches 0.9 at half the time of the linear one (squares)."
- Axis labels with quantity and unit. Legends where there is more than one data set. Fonts readable at print size.
- Arrange panels so the comparison that matters is side by side on a shared axis.
- Tables only for values the reader will look up; trends go in a figure.

## LaTeX output

When writing LaTeX: `\cite{key}` with keys from the verification log, `\ref` for figures and equations, `--` for number ranges, never `---`, and `~` before a reference (`Fig.~\ref{fig:gain}`). Use the document's existing macros and bibliography setup. Run `check.py` with `--format latex`; it strips maths, comments and citations before checking the prose.
