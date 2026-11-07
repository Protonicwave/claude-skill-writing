# Tells and what to write instead

A revision checklist, built from corpus studies of machine-written text and from editors who review it. Three cautions shape every entry.

- **The evidence is about populations, not single texts.** Kobak et al. (Science Advances, 2025) measured excess vocabulary across 15 million PubMed abstracts; no single word proves anything. What reads as machine-made is clustering: several tells in one paragraph.
- **Word lists go stale; behaviours do not.** "Delve" fell sharply in 2025 as models changed. The replacement behaviours below hold whatever the current fashion.
- **Fixing symptoms is not the goal.** A tell usually marks a sentence with no specific claim. Deleting the word without finding the claim leaves an empty sentence. Find the claim.

`scripts/check.py` catches the mechanical cases. Everything else is judgement.

## Vocabulary

| Tell | Write instead |
|---|---|
| Style verbs: delve, underscore, showcase, highlight, foster, leverage, harness, elucidate, unveil, bolster, garner, embark, streamline, utilise | The operation that happened: measured, fitted, derived, showed, found, used, increased. If a sentence only says something "highlights" a point, state the point. |
| Evaluative adjectives: crucial, pivotal, intricate, meticulous, comprehensive, seamless, invaluable, notable, remarkable, groundbreaking, transformative, unprecedented | The measurable property or the reason. "A crucial parameter" becomes "the parameter the fit is most sensitive to: a 1% change moves the threshold by 4 mW". Never praise your own work. |
| Abstract nouns: realm, tapestry, interplay, insights, avenues, endeavours, nuances | Name the thing. "The interplay between nonlinearity and annealing" becomes "how the nonlinear term changes which minimum the anneal finds". |
| Copula avoidance: serves as, stands as, functions as, boasts, features | Is, are, has. |
| Sentence-initial Additionally, Moreover, Furthermore, Notably, Importantly | Usually delete. Where the logic turns, use the specific link: because, so, but, for example. |
| Downtoners and stacked hedges: somewhat, relatively, arguably, may potentially | One qualifier with its reason: "within the 2% calibration uncertainty". |

**Physics exemption.** Many listed words are technical terms: potential, complex, robust, precise, distinct, conditions, analysis, approach, primary, landscape (energy landscape), enhance (enhancement factor), elevated (elevated temperature). A word stays when it carries its technical sense or is the plainest word available. It goes when it is decoration.

## Sentence construction

| Tell | Evidence | Write instead |
|---|---|---|
| Trailing "-ing" clause claiming significance: "..., highlighting the importance of X", "..., ensuring Y" | Present-participle clauses at 2 to 5 times the human rate (Reinhart et al., PNAS 2025) | End the sentence on the fact. If the consequence matters, give it its own sentence with a subject, a finite verb and how you know. |
| Nominalisation: "the implementation of", "performed an analysis" | 1.5 to 2 times the human rate (Reinhart et al.) | Action in the verb, actor in the subject: "the code implements", "we analysed". |
| Negative parallelism: "not just X, but Y", "it's not X, it's Y" | Editors' observation; no corpus count | State Y. Mention X only if a reader would believe it, and say why it is wrong. |
| Rule of three: three adjectives, three parallel phrases | Editors' observation | Use as many items as the content has. Two is fine; one is often best. |
| Uniform rhythm: sentences clustered at 15 to 20 words | Flatter than human text in 32 of 45 tested model settings (Lanzo and Angelo, 2026) | Length follows content. Do not insert short sentences purely for effect. |
| Elegant variation: "sample", "specimen", "crystal" for one object | Repetition penalties in training | One term per concept, repeated. Three names read as three objects. |
| Vague relation: associated with, linked to, plays a role in | Editors' observation | The actual relation: causes, scales as, correlates with (give r), is a special case of. |
| Em dashes | Share of medRxiv discussions with one rose from 4% to 20% between 2023 and 2025 (Czuma, 2026) | None. Comma, brackets, colon or full stop, chosen by the logic. |

**Do not purge the passive.** Models use the agentless passive at about half the human rate. Methods sections use it legitimately ("the sample was cooled to 4 K"). Use the passive when the actor does not matter and the object is the topic; the active when the actor matters.

## Paragraphs and structure

| Tell | Write instead |
|---|---|
| Restating summary: "In summary", "In conclusion", "Overall" closing a paragraph or section | End on the newest, most important information. A report's conclusion links results back to the aims and adds nothing new. |
| Formulaic "challenges and future directions" close: "Despite these challenges..." | The specific limitation, its size, and the specific next measurement. |
| Didactic frames: "It is important to note that", "It is worth noting" | Delete the frame and state the note. Position shows importance. |
| Corrective frames: "should not be confused with", "does not by itself establish" | Say what the evidence does establish, with its uncertainty. Disambiguate only a real near-homonym, once. |
| Every section the same shape, the same balance of praise and caveat | Shape each section by its job. Results report; Discussion interprets. |
| Too few stance markers | Real stance where the writer has one: "we expected", "this surprised us", "I think". Models underuse these. |
| Empty signposting: "In this section we will explore" | One orienting sentence per long section, carrying content. |

## Formatting

- No bold in running prose. Italicise a term once, at its definition.
- No inline-header bullet lists ("Accuracy: ..."). Write paragraphs; list only discrete parallel items.
- Sentence-case headings that follow the department's structure.
- No emoji, decorative dividers or leftover Markdown (`**`, `#`) in Word or LaTeX output.

## Content

| Tell | Write instead |
|---|---|
| Inflated significance of ordinary facts | The result and its size. Let numbers and comparisons carry importance. |
| Vague attribution: "studies show", "experts argue" | The specific paper for the specific claim, verified under `sources.md`. No source to hand: `[CITATION NEEDED: claim]`. |
| Invented specifics: references, DOIs, figures, dates | Never. Every number traces to the student's data or a verified source. |
| Availability hedges: "while specific details are limited" | Say exactly what is missing and why it matters, or leave it out. |
| Interpretation with no mechanism | Each interpretive claim answers "how do you know?" |
| Generic examples: "in many applications" | The student's own system, numbers and apparatus. |
| False balance: equal weight to a strong and a weak explanation | Weight by evidence. If one fits within uncertainty and another does not, say so. |
| Chatbot residue: "Certainly", "I hope this helps", "Great question" | Never in delivered text. |
| Promotional tone | Neutral register; confidence comes from evidence. |

## Not tells

Perfect grammar, formal register, transition words used where the logic turns, plain prose and long sentences are all human. Editors list them as unreliable signs. Readers also judge machine text near chance. The checklist exists to make the writing better, and better writing happens to read as human.
