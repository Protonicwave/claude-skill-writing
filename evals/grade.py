"""Score the programmatic checks of writing-skill eval runs.

Usage: python evals/grade.py RUN_DIR [RUN_DIR ...] [--evals PATH]

A run directory follows the skill-creator layout: it holds
outputs/deliverable.md, and its parent holds eval_metadata.json naming the
eval_id. The checks for that eval come from evals.json. Each result is merged
into RUN_DIR/grading.json as an expectation whose text starts with AUTO_PREFIX,
so judgement expectations written by a grader are kept. Exit 0 when every run
was graded, 2 when an input cannot be read.
"""

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

DEFAULT_EVALS = Path(__file__).resolve().parent / "evals.json"
CHECKER = Path(__file__).resolve().parent.parent / "writing" / "scripts" / "check.py"
DELIVERABLE = Path("outputs") / "deliverable.md"
AUTO_PREFIX = "auto: "
MAX_INPUT_BYTES = 1_000_000
CHECKER_TIMEOUT_SECONDS = 60
# Integers this small are list positions, counts and ordinals far more often
# than invented results, so they are not traced back to the inputs.
SMALL_INTEGER_LIMIT = 10
MAX_LISTED_ITEMS = 10

WORD = re.compile(r"[A-Za-z0-9][\w'\u2019-]*")
# The skill stamps markers and logs with the date it checked a source, so
# ISO dates are written at run time and cannot come from the inputs.
ISO_DATE = re.compile(r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b")
NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
THOUSANDS = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
HASHTAG = re.compile(r"(?<![\w#&])#[A-Za-z]\w*")
SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*(?=\s|$)")
NOT_PROSE_BLOCK = re.compile(r"^\s*(?:#|[-*+]\s|\d+[.)]\s|>|```|\|)")

FormatName = Literal["plain", "markdown", "latex"]


@dataclass(frozen=True, slots=True)
class CheckerClean:
    format: FormatName


@dataclass(frozen=True, slots=True)
class MaxWords:
    limit: int


@dataclass(frozen=True, slots=True)
class NumbersFromInputs:
    pass


@dataclass(frozen=True, slots=True)
class ForbiddenPhrases:
    phrases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContainsAny:
    phrases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MaxHashtags:
    limit: int


@dataclass(frozen=True, slots=True)
class MaxOneSentenceParagraphShare:
    share: float


Check = (
    CheckerClean
    | MaxWords
    | NumbersFromInputs
    | ForbiddenPhrases
    | ContainsAny
    | MaxHashtags
    | MaxOneSentenceParagraphShare
)


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: int
    expectations: tuple[str, ...]
    checks: tuple[Check, ...]
    input_text: str


@dataclass(frozen=True, slots=True)
class Expectation:
    text: str
    passed: bool
    evidence: str


def _field[T](record: Mapping[str, object], name: str, kind: type[T]) -> T:
    value = record.get(name)
    # JSON true and false load as bool, which Python treats as an int.
    if isinstance(value, bool) or not isinstance(value, kind):
        raise ValueError(f"expected {name} to be {kind.__name__}, got {value!r}")
    return value


def _fraction(record: Mapping[str, object], name: str) -> float:
    value = record.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"expected {name} to be a number from 0 to 1, got {value!r}")
    return float(value)


def _strings(record: Mapping[str, object], name: str) -> tuple[str, ...]:
    values = _field(record, name, list)
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError(
            f"expected {name} to be a list of non-empty strings, got {values!r}"
        )
    return tuple(values)


def _format_name(spec: Mapping[str, object]) -> FormatName:
    name = _field(spec, "format", str)
    if name not in ("plain", "markdown", "latex"):
        raise ValueError(f"expected format plain, markdown or latex, got {name!r}")
    return cast(FormatName, name)


CHECK_PARSERS: dict[str, Callable[[Mapping[str, object]], Check]] = {
    "checker_clean": lambda spec: CheckerClean(_format_name(spec)),
    "max_words": lambda spec: MaxWords(_field(spec, "limit", int)),
    "numbers_from_inputs": lambda spec: NumbersFromInputs(),
    "forbidden_phrases": lambda spec: ForbiddenPhrases(_strings(spec, "phrases")),
    "contains_any": lambda spec: ContainsAny(_strings(spec, "phrases")),
    "max_hashtags": lambda spec: MaxHashtags(_field(spec, "limit", int)),
    "max_one_sentence_paragraph_share": lambda spec: MaxOneSentenceParagraphShare(
        _fraction(spec, "share")
    ),
}


def _parse_check(spec: object) -> Check:
    if not isinstance(spec, dict):
        raise ValueError(f"expected a check object, got {spec!r}")
    kind = spec.get("kind")
    parser = CHECK_PARSERS.get(kind) if isinstance(kind, str) else None
    if parser is None:
        raise ValueError(f"unknown check kind {kind!r}")
    return parser(spec)


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{path} is larger than {MAX_INPUT_BYTES} bytes")
    return path.read_text(encoding="utf-8")


def _parse_case(record: object, files_root: Path) -> EvalCase:
    if not isinstance(record, dict):
        raise ValueError(f"expected an eval object, got {record!r}")
    prompt = _field(record, "prompt", str)
    _field(record, "expected_output", str)
    texts = [prompt]
    for name in _strings(record, "files"):
        path = files_root / name
        if not path.is_file():
            raise ValueError(f"input file {path} does not exist")
        texts.append(_read_text(path))
    return EvalCase(
        id=_field(record, "id", int),
        expectations=_strings(record, "expectations"),
        checks=tuple(_parse_check(spec) for spec in _field(record, "checks", list)),
        input_text="\n".join(texts),
    )


def load_cases(path: Path) -> dict[int, EvalCase]:
    """Parse evals.json into cases by id; raise ValueError on any malformed field."""
    document = json.loads(_read_text(path))
    if not isinstance(document, dict):
        raise ValueError(f"expected {path} to hold a JSON object")
    _field(document, "skill_name", str)
    cases: dict[int, EvalCase] = {}
    for record in _field(document, "evals", list):
        parsed = _parse_case(record, path.parent)
        if parsed.id in cases:
            raise ValueError(f"duplicate eval id {parsed.id}")
        cases[parsed.id] = parsed
    return cases


def _numbers(text: str) -> set[str]:
    found = set()
    for match in NUMBER.finditer(ISO_DATE.sub(" ", text)):
        number = match.group()
        if THOUSANDS.fullmatch(number):
            number = number.replace(",", "")
        if number.isdigit() and int(number) <= SMALL_INTEGER_LIMIT:
            continue
        found.add(number)
    return found


def _is_one_sentence(block: str) -> bool:
    return len(SENTENCE_END.findall(block.strip())) <= 1


def _prose_blocks(text: str) -> list[str]:
    blocks = (block.strip() for block in re.split(r"\n\s*\n", text))
    return [
        block
        for block in blocks
        if block and not NOT_PROSE_BLOCK.match(block) and not HASHTAG.fullmatch(block)
    ]


def _phrases_found(phrases: tuple[str, ...], text: str) -> list[str]:
    lowered = text.casefold()
    return [phrase for phrase in phrases if phrase.casefold() in lowered]


def _checker_errors(deliverable: str, fmt: FormatName) -> list[str]:
    # UTF-8 mode, because check.py reads standard input in the console's code page.
    completed = subprocess.run(  # noqa: S603  fixed interpreter and script, no shell
        [sys.executable, "-I", "-X", "utf8", str(CHECKER), "-", "--format", fmt],
        input=deliverable,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=CHECKER_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise RuntimeError(
            f"check.py exited {completed.returncode}: {completed.stderr}"
        )
    return [line for line in completed.stdout.splitlines() if ": error [" in line]


def _listed(items: list[str]) -> str:
    return ", ".join(items[:MAX_LISTED_ITEMS]) or "none"


def _describe(check: Check) -> str:
    """The expectation text a check is reported under, AUTO_PREFIX included."""
    match check:
        case CheckerClean(fmt):
            description = f"check.py ({fmt}) reports no errors"
        case MaxWords(limit):
            description = f"at most {limit} words"
        case NumbersFromInputs():
            description = "every number appears in the prompt or input files"
        case ForbiddenPhrases(phrases):
            description = f"avoids: {'; '.join(phrases)}"
        case ContainsAny(phrases):
            description = f"contains one of: {'; '.join(phrases)}"
        case MaxHashtags(limit):
            description = f"at most {limit} hashtags"
        case MaxOneSentenceParagraphShare(share):
            description = f"at most {share:.0%} of prose paragraphs are one sentence"
    return f"{AUTO_PREFIX}{description}"


def _short_paragraph_verdict(share: float, deliverable: str) -> tuple[bool, str]:
    blocks = _prose_blocks(deliverable)
    single = sum(_is_one_sentence(block) for block in blocks)
    measured = single / len(blocks) if blocks else 0.0
    return (
        measured <= share,
        f"{single} of {len(blocks)} prose paragraphs are one sentence",
    )


def _verdict(check: Check, deliverable: str, input_text: str) -> tuple[bool, str]:
    match check:
        case CheckerClean(fmt):
            errors = _checker_errors(deliverable, fmt)
            verdict = not errors, _listed(errors)
        case MaxWords(limit):
            count = len(WORD.findall(deliverable))
            verdict = count <= limit, f"{count} words"
        case NumbersFromInputs():
            unsourced = sorted(_numbers(deliverable) - _numbers(input_text))
            verdict = (
                not unsourced,
                f"not in prompt or input files: {_listed(unsourced)}",
            )
        case ForbiddenPhrases(phrases):
            found = _phrases_found(phrases, deliverable)
            verdict = not found, f"found: {_listed(found)}"
        case ContainsAny(phrases):
            found = _phrases_found(phrases, deliverable)
            verdict = bool(found), f"found: {_listed(found)}"
        case MaxHashtags(limit):
            tags = HASHTAG.findall(deliverable)
            verdict = len(tags) <= limit, f"found: {_listed(tags)}"
        case MaxOneSentenceParagraphShare(share):
            verdict = _short_paragraph_verdict(share, deliverable)
    return verdict


def score(check: Check, deliverable: str, input_text: str) -> Expectation:
    """Decide one check against the deliverable text."""
    passed, evidence = _verdict(check, deliverable, input_text)
    return Expectation(_describe(check), passed, evidence)


def _grade_run(run_dir: Path, cases: Mapping[int, EvalCase]) -> list[Expectation]:
    """Score every check of the run's eval; a missing deliverable fails them all."""
    metadata_path = run_dir.parent / "eval_metadata.json"
    metadata = json.loads(_read_text(metadata_path))
    if not isinstance(metadata, dict):
        raise ValueError(f"expected {metadata_path} to hold a JSON object")
    eval_id = _field(metadata, "eval_id", int)
    if eval_id not in cases:
        raise ValueError(
            f"eval_id {eval_id!r} in {run_dir.parent} is not in the eval set"
        )
    case = cases[eval_id]
    deliverable_path = run_dir / DELIVERABLE
    if not deliverable_path.is_file():
        missing = f"{DELIVERABLE.as_posix()} is missing"
        return [Expectation(_describe(check), False, missing) for check in case.checks]
    deliverable = _read_text(deliverable_path)
    return [score(check, deliverable, case.input_text) for check in case.checks]


def _merged_grading(
    existing: dict[str, object], scored: list[Expectation]
) -> dict[str, object]:
    """Swap in the automatic expectations and recount the summary."""
    kept = [
        entry
        for entry in _field(existing, "expectations", list)
        if not (
            isinstance(entry, dict)
            and str(entry.get("text", "")).startswith(AUTO_PREFIX)
        )
    ]
    expectations = kept + [
        {"text": item.text, "passed": item.passed, "evidence": item.evidence}
        for item in scored
    ]
    passed = sum(
        1
        for entry in expectations
        if isinstance(entry, dict) and entry.get("passed") is True
    )
    total = len(expectations)
    summary = {
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "pass_rate": round(passed / total, 2) if total else 0.0,
    }
    return {**existing, "expectations": expectations, "summary": summary}


def _existing_grading(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"expectations": []}
    existing = json.loads(_read_text(path))
    if not isinstance(existing, dict):
        raise ValueError(f"expected {path} to hold a JSON object")
    return existing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score eval runs' programmatic checks."
    )
    parser.add_argument(
        "run_dirs", nargs="+", type=Path, help="run directories to grade"
    )
    parser.add_argument(
        "--evals", type=Path, default=DEFAULT_EVALS, help="the eval set"
    )
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.evals)
        for run_dir in args.run_dirs:
            grading_path = run_dir / "grading.json"
            grading = _merged_grading(
                _existing_grading(grading_path), _grade_run(run_dir, cases)
            )
            grading_path.write_text(
                json.dumps(grading, indent=2) + "\n", encoding="utf-8"
            )
            summary = cast(dict[str, int], grading["summary"])
            print(f"{run_dir}: {summary['passed']} of {summary['total']} passed")
    except (OSError, ValueError) as err:
        print(f"cannot grade: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
