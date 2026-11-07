"""Flag the measurable signs of machine-written prose in a draft.

Usage:
    check.py <path> [--format plain|markdown|latex]
    check.py - [--format ...]        read the draft from standard input

The format follows the extension (.md is markdown, .tex is latex, anything
else is plain) unless --format is given. Exits 1 if any error is found, 2 if
the draft cannot be read, 0 otherwise.

Errors are never acceptable in a finished draft. Warnings need judgement:
physics uses some listed words in their technical sense, and a hedge or a
connective is sometimes the right word.
"""

from __future__ import annotations

import argparse
import io
import re
import statistics
import sys
from bisect import bisect_right
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

MAX_DRAFT_CHARACTERS = 5_000_000
PARAGRAPH_RHYTHM_MIN_SENTENCES = 5
PARAGRAPH_RHYTHM_MIN_SPREAD = 0.25
DOCUMENT_RHYTHM_MIN_SENTENCES = 15
# Admired human prose spreads sentence length by 0.46 to 0.71 of the mean;
# below 0.35 across a whole document the rhythm reads as generated.
DOCUMENT_RHYTHM_MIN_SPREAD = 0.35


class Format(StrEnum):
    PLAIN = "plain"
    MARKDOWN = "markdown"
    LATEX = "latex"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Issue:
    line: int
    rule: str
    severity: Severity
    message: str


@dataclass(frozen=True, slots=True)
class PatternRule:
    """A regular expression whose matches are issues. A group named `hit`,
    when present, is the part reported; the rest is context."""

    name: str
    severity: Severity
    pattern: re.Pattern[str]
    message: str  # formatted with {hit}


LineKind = Literal["text", "item", "heading"]


@dataclass(frozen=True, slots=True)
class ProseLine:
    number: int
    text: str
    kind: LineKind


@dataclass(frozen=True, slots=True)
class Paragraph:
    lines: tuple[ProseLine, ...]

    @property
    def is_heading(self) -> bool:
        return self.lines[0].kind == "heading"

    @property
    def text(self) -> str:
        return " ".join(line.text for line in self.lines)

    def line_at(self, offset: int) -> int:
        starts: list[int] = []
        position = 0
        for line in self.lines:
            starts.append(position)
            position += len(line.text) + 1
        return self.lines[bisect_right(starts, offset) - 1].number


def _rule(
    name: str, severity: Severity, pattern: str, message: str, *, flags: int = 0
) -> PatternRule:
    return PatternRule(name, severity, re.compile(pattern, flags), message)


ERR, WARN, NOCASE = Severity.ERROR, Severity.WARNING, re.IGNORECASE
DASH_FIX = "use a comma, colon, brackets or a full stop"

DASH_RULES: dict[Format, tuple[PatternRule, ...]] = {
    Format.PLAIN: (
        _rule("dash", ERR, "\u2014", f"em dash: {DASH_FIX}"),
        # An en dash with no space either side is a range or a joined name
        # (10 to 20, Hartree and Fock), which typesetting allows.
        _rule(
            "dash",
            ERR,
            r"\s\u2013|\u2013\s",
            f"en dash used as punctuation: {DASH_FIX}",
        ),
        _rule(
            "dash",
            ERR,
            r"(?<=[A-Za-z)])\s+-\s+(?=[A-Za-z(])",
            f"spaced hyphen used as a dash: {DASH_FIX}",
        ),
    ),
    Format.LATEX: (
        _rule("dash", ERR, "\u2014|(?<!-)---(?!-)", f"em dash: {DASH_FIX}"),
        _rule(
            "dash",
            ERR,
            r"\s\u2013|\u2013\s|\s--(?!-)|(?<!-)--\s",
            f"en dash used as punctuation: {DASH_FIX}",
        ),
        _rule(
            "dash",
            ERR,
            r"(?<=[A-Za-z)])\s+-\s+(?=[A-Za-z(])",
            f"spaced hyphen used as a dash: {DASH_FIX}",
        ),
    ),
}
DASH_RULES[Format.MARKDOWN] = DASH_RULES[Format.PLAIN]

DECORATIVE_WORDS = (
    r"delv(?:e|es|ed|ing)|underscor(?:e|es|ed|ing)|showcas(?:e|es|ed|ing)|foster(?:s|ed|ing)?"
    r"|leverag(?:e|es|ed|ing)|harness(?:es|ed|ing)?|elucidat(?:e|es|ed|ing)|unveil(?:s|ed|ing)?"
    r"|bolster(?:s|ed|ing)?|garner(?:s|ed|ing)?|streamlin(?:e|es|ed|ing)|empower(?:s|ed|ing)?"
    r"|embark(?:s|ed|ing)?|boast(?:s|ed|ing)?|highlight(?:s|ed)?|utili[sz](?:e|es|ed|ing|ation)"
    r"|tapestry|testament|realms?|interplay|insights?|endeavou?rs?|intricac(?:y|ies)|avenues?"
    r"|pivotal|crucial(?:ly)?|intricate(?:ly)?|meticulous(?:ly)?|commendable|seamless(?:ly)?"
    r"|groundbreaking|transformative|multifaceted|invaluable|noteworthy|notabl[ey]|paramount"
    r"|vibrant|nuanced|unparalleled|unprecedented|remarkabl[ey]|profound(?:ly)?|vital"
    r"|comprehensive(?:ly)?|cutting-edge|game-?changing|holistic|synerg(?:y|ies)"
)
SIGNIFICANCE_VERBS = (
    r"highlighting|underscoring|emphasi[sz]ing|showcasing|signall?ing|marking"
    r"|paving the way|ensuring|contributing to|fostering|reinforcing|cementing"
    r"|solidifying|setting the stage|underlining|illustrating|demonstrating"
)
STOCK_PHRASES = (
    r"it(?: is|'s|\u2019s) (?:important|worth|crucial|essential)"
    r" (?:to note|noting|to mention|to remember)"
    r"|it (?:should|must) be noted"
    r"|play(?:s|ed|ing)? an? (?:crucial|key|vital|pivotal|significant|important|central"
    r"|essential|critical) role"
    r"|(?:serves?|served|serving|stands?|stood) as|a testament to"
    r"|navigat\w* the complexit\w*|deep dive|in today(?:'s|\u2019s)|ever-evolving"
    r"|paradigm shift|despite these challenges|(?:has|have|had) emerged as"
    r"|not (?:just|only|merely|simply)\b[^.?!]{1,80}?\bbut\b"
    r"|(?:it(?:'s|\u2019s)|it is|this is) not \w+(?: \w+){0,3},"
    r" (?:it(?:'s|\u2019s)|but)"
    r"|in conclusion|in summary|to summari[sz]e|to sum up"
    r"|while specific details are limited|based on (?:the )?available information"
    r"|(?:studies|research) (?:has |have )?(?:shows?|shown|suggests?)"
    r"|(?:experts|scientists|researchers) (?:argue|agree|say|believe)"
    r"|should not be confused with|does not by itself"
)
CONNECTIVE_OPENERS = (
    r"Additionally|Moreover|Furthermore|Notably|Importantly|Interestingly|Crucially"
    r"|Ultimately|Overall|In addition"
)
US_WORDS = (
    r"colors?|colored|coloring|behaviors?|behavioral|favors?|favored|favorite|honors?"
    r"|neighbors?|neighboring|labors?|centers?|centered|centering|fibers?|aluminum|gray"
    r"|modeling|modeled|labeled|labeling|traveled|traveling|canceled|canceling|signaling"
    r"|signaled|fueled|fueling|catalogs?|defense|skeptical|artifacts?"
)

PROSE_RULES: tuple[PatternRule, ...] = (
    _rule(
        "emoji",
        ERR,
        "[\U0001f300-\U0001faff\u2705\u2728\u274c\u2b50]",
        "emoji in prose",
    ),
    _rule(
        "chatbot",
        ERR,
        r"\bI hope this helps\b|\bas an AI\b|\bas a (?:large )?language model\b"
        r"|\bgreat question\b|\bcertainly!|\bI(?:'d|\u2019d| would) be happy to help\b"
        r"|\bknowledge cut-?off\b",
        "chatbot phrase '{hit}': delete it",
        flags=NOCASE,
    ),
    _rule(
        "vocabulary",
        WARN,
        rf"\b(?:{DECORATIVE_WORDS})\b",
        "decorative word '{hit}': say the specific thing instead",
        flags=NOCASE,
    ),
    _rule(
        "significance-clause",
        WARN,
        rf",\s+(?P<hit>(?:{SIGNIFICANCE_VERBS})\b)",
        "trailing clause '{hit}' claims significance: end on the fact, or give the"
        " consequence its own sentence",
        flags=NOCASE,
    ),
    _rule(
        "stock-phrase",
        WARN,
        rf"\b(?:{STOCK_PHRASES})\b",
        "stock phrase '{hit}': state the point directly",
        flags=NOCASE,
    ),
    _rule(
        "connective-opener",
        WARN,
        rf"(?:^|[.!?][\"'\u201d\u2019)\]]?\s+)(?P<hit>{CONNECTIVE_OPENERS}),",
        "sentence opens with '{hit}': use the specific logical link, or none",
    ),
    _rule(
        "hedge-stack",
        WARN,
        r"\b(?:may|might|could|can) (?:potentially|possibly|perhaps|conceivably)\b"
        r"|\b(?:potentially|possibly) (?:may|might|could)\b",
        "stacked hedge '{hit}': hedge once, where the uncertainty is",
        flags=NOCASE,
    ),
    _rule(
        "us-spelling",
        WARN,
        # Words built on size, prize and seize are spelt with z in UK English too.
        r"\b(?!(?:re|over|under|down|up)?(?:si|pri|sei|capsi|mai|bai)z)\w*(?:iz|yz)"
        r"(?:e|es|ed|er|ers|ing|ation|ations|able)\b"
        rf"|\b(?:{US_WORDS})\b",
        "US spelling '{hit}': use the UK form",
        flags=NOCASE,
    ),
    _rule(
        "unresolved-marker",
        WARN,
        r"\[(?:UNVERIFIED|CITATION NEEDED)[^\]]*\]",
        "unresolved marker '{hit}': verify the source or cut the claim",
    ),
)
MARKDOWN_RULES: tuple[PatternRule, ...] = (
    _rule(
        "bold-in-prose",
        WARN,
        r"\*\*[^*]+\*\*|__[^_]+__",
        "bold in running prose: drop it, or italicise a term at its definition",
    ),
)

# The `.` inside these is not a sentence end.
ABBREVIATION = re.compile(
    r"\b(?:e\.g|i\.e|et al|etc|cf|vs|approx|Figs?|Eqs?|Refs?|Secs?|Ch|Dr|Prof"
    r"|Mrs?|Ms|No|Vol|pp|St)\."
    # A lone capital is an initial (R. P. Feynman) unless a number precedes it (2 W.).
    r"|(?<!\d\s)\b[A-Z]\.(?=\s+[A-Z])"
)
SENTENCE_BREAK = re.compile(
    r"(?<=[.!?])[\"'\u201d\u2019)\]]*\s+(?=[\"'\u201c\u2018(\[]?[A-Z0-9])"
)
WORD = re.compile(r"[A-Za-z0-9][\w'\u2019-]*")
PROTECTED_DOT = "\x00"


def split_sentences(text: str) -> list[str]:
    protected = ABBREVIATION.sub(
        lambda m: m.group(0).replace(".", PROTECTED_DOT), text.strip()
    )
    if not protected:
        return []
    return [
        part.replace(PROTECTED_DOT, ".")
        for part in SENTENCE_BREAK.split(protected)
        if part.strip()
    ]


def _blank_keeping_lines(match: re.Match[str]) -> str:
    """Replace a span with nothing but its newlines, so line numbers survive."""
    return "\n" * match.group(0).count("\n") or " "


LATEX_BLOCK = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|math|tabular|tikzpicture"
    r"|verbatim|lstlisting|minted)\*?\}.*?\\end\{\1\*?\}"
    r"|\\\[.*?\\\]|\$\$.*?\$\$",
    re.DOTALL,
)
LATEX_COMMENT = re.compile(r"(?<!\\)%.*")
LATEX_INLINE_MATHS = re.compile(r"(?<!\\)\$[^$]*(?<!\\)\$|\\\(.*?\\\)")
LATEX_DROPPED_COMMAND = re.compile(
    r"\\(?:cite\w*|ref|eqref|autoref|[cC]ref|label|includegraphics|url|input|include|bibliography"
    r"|bibliographystyle|usepackage|documentclass|begin|end|[hv]space)\*?(?:\[[^\]]*\])*\{[^}]*\}"
)
LATEX_HEADING = re.compile(
    r"^\s*\\(?:part|chapter|(?:sub){0,2}section|paragraph)\*?\{(.*)\}\s*$"
)
LATEX_ITEM = re.compile(r"^\s*\\item\b(?:\[[^\]]*\])?")
LATEX_COMMAND = re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?")

MARKDOWN_FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1[^\n]*$", re.DOTALL | re.MULTILINE)
MARKDOWN_INLINE_CODE = re.compile(r"`[^`\n]*`")
MARKDOWN_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_HEADING = re.compile(r"^\s*#{1,6}\s+")
MARKDOWN_SKIPPED_LINE = re.compile(r"^\s*(?:\||(?:-{3,}|\*{3,}|_{3,})\s*$)")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
QUOTE_MARKER = re.compile(r"^\s*>\s?")


def _latex_line(number: int, raw: str) -> ProseLine:
    line = LATEX_INLINE_MATHS.sub(" ", LATEX_COMMENT.sub("", raw))
    if heading := LATEX_HEADING.match(line):
        return ProseLine(number, heading.group(1), "heading")
    kind: LineKind = "item" if LATEX_ITEM.match(line) else "text"
    line = LATEX_DROPPED_COMMAND.sub(" ", LATEX_ITEM.sub("", line))
    line = LATEX_COMMAND.sub("", line).replace("~", " ").replace("\\%", "%")
    return ProseLine(number, re.sub(r"[{}]", "", line).strip(), kind)


def _markdown_line(number: int, raw: str) -> ProseLine:
    line = MARKDOWN_INLINE_CODE.sub(" ", raw)
    if MARKDOWN_SKIPPED_LINE.match(line):
        return ProseLine(number, "", "text")
    if MARKDOWN_HEADING.match(line):
        return ProseLine(number, MARKDOWN_HEADING.sub("", line).strip(), "heading")
    return _plain_line(number, QUOTE_MARKER.sub("", line))


def _plain_line(number: int, raw: str) -> ProseLine:
    kind: LineKind = "item" if LIST_MARKER.match(raw) else "text"
    return ProseLine(number, LIST_MARKER.sub("", raw).strip(), kind)


def prose_lines(text: str, fmt: Format) -> list[ProseLine]:
    """Every line of the draft with markup removed, numbered from 1."""
    if fmt is Format.LATEX:
        text = LATEX_BLOCK.sub(_blank_keeping_lines, text)
        to_prose = _latex_line
    elif fmt is Format.MARKDOWN:
        text = MARKDOWN_COMMENT.sub(
            _blank_keeping_lines, MARKDOWN_FENCE.sub(_blank_keeping_lines, text)
        )
        to_prose = _markdown_line
    else:
        to_prose = _plain_line
    return [
        to_prose(number, raw) for number, raw in enumerate(text.splitlines(), start=1)
    ]


def paragraphs(lines: list[ProseLine]) -> list[Paragraph]:
    groups: list[list[ProseLine]] = []
    previous_blank = True
    for line in lines:
        if not line.text:
            previous_blank = True
            continue
        if previous_blank or line.kind != "text" or groups[-1][-1].kind == "heading":
            groups.append([])
        groups[-1].append(line)
        previous_blank = False
    return [Paragraph(tuple(group)) for group in groups]


def _pattern_issues(
    paragraph: Paragraph, rules: tuple[PatternRule, ...]
) -> list[Issue]:
    text = paragraph.text
    issues = []
    for rule in rules:
        group: str | int = "hit" if "hit" in rule.pattern.groupindex else 0
        for match in rule.pattern.finditer(text):
            line = paragraph.line_at(match.start(group))
            issues.append(
                Issue(
                    line,
                    rule.name,
                    rule.severity,
                    rule.message.format(hit=match.group(group).strip()),
                )
            )
    return issues


def _spread(sentences: list[str]) -> tuple[float, float]:
    """Mean words per sentence, and standard deviation as a fraction of the mean."""
    lengths = [len(WORD.findall(sentence)) for sentence in sentences]
    mean = statistics.fmean(lengths)
    return mean, (statistics.pstdev(lengths) / mean if mean else 0.0)


def _rhythm_issue(paragraph: Paragraph) -> Issue | None:
    sentences = split_sentences(paragraph.text)
    if len(sentences) < PARAGRAPH_RHYTHM_MIN_SENTENCES:
        return None
    mean, spread = _spread(sentences)
    if spread >= PARAGRAPH_RHYTHM_MIN_SPREAD:
        return None
    message = (
        f"{len(sentences)} sentences of about {mean:.0f} words each"
        f" (spread {spread:.2f}): let length follow the content"
    )
    return Issue(paragraph.lines[0].number, "rhythm", WARN, message)


def _document_rhythm_issue(body: list[Paragraph]) -> Issue | None:
    sentences = [
        sentence for paragraph in body for sentence in split_sentences(paragraph.text)
    ]
    if len(sentences) < DOCUMENT_RHYTHM_MIN_SENTENCES:
        return None
    mean, spread = _spread(sentences)
    if spread >= DOCUMENT_RHYTHM_MIN_SPREAD:
        return None
    message = (
        f"sentence length barely varies across {len(sentences)} sentences "
        f"(mean {mean:.0f} words, spread {spread:.2f}; admired prose sits above 0.45)"
    )
    return Issue(body[0].lines[0].number, "document-rhythm", WARN, message)


def find_issues(text: str, fmt: Format) -> list[Issue]:
    """All issues in a draft, ordered by line. Pure: reads nothing, writes nothing."""
    rules = (
        DASH_RULES[fmt]
        + PROSE_RULES
        + (MARKDOWN_RULES if fmt is Format.MARKDOWN else ())
    )
    all_paragraphs = paragraphs(prose_lines(text, fmt))
    body = [paragraph for paragraph in all_paragraphs if not paragraph.is_heading]
    issues = [
        issue
        for paragraph in all_paragraphs
        for issue in _pattern_issues(paragraph, rules)
    ]
    issues += [issue for paragraph in body if (issue := _rhythm_issue(paragraph))]
    if document_issue := _document_rhythm_issue(body):
        issues.append(document_issue)
    return sorted(issues, key=lambda issue: issue.line)


def format_for(path: str) -> Format:
    suffix = Path(path).suffix.lower()
    return {
        ".md": Format.MARKDOWN,
        ".markdown": Format.MARKDOWN,
        ".tex": Format.LATEX,
    }.get(suffix, Format.PLAIN)


def read_draft(path: str) -> str:
    if path == "-":
        text = sys.stdin.read(MAX_DRAFT_CHARACTERS + 1)
    else:
        with Path(path).open(encoding="utf-8") as handle:
            text = handle.read(MAX_DRAFT_CHARACTERS + 1)
    if len(text) > MAX_DRAFT_CHARACTERS:
        raise ValueError(
            f"draft is over {MAX_DRAFT_CHARACTERS} characters; check it in parts"
        )
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Flag the measurable signs of machine-written prose."
    )
    parser.add_argument("path", help="the draft to check, or - for standard input")
    parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in Format],
        help="override the format the extension implies",
    )
    args = parser.parse_args(argv)

    try:
        text = read_draft(args.path)
    except (OSError, UnicodeDecodeError, ValueError) as err:
        print(f"cannot check {args.path}: {err}", file=sys.stderr)
        return 2

    # A console on a legacy code page cannot print every character a draft may contain.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")
    name = "<stdin>" if args.path == "-" else args.path
    issues = find_issues(
        text, Format(args.format) if args.format else format_for(args.path)
    )
    for issue in issues:
        print(f"{name}:{issue.line}: {issue.severity} [{issue.rule}] {issue.message}")
    return 1 if any(issue.severity is Severity.ERROR for issue in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
