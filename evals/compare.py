"""Compare an eval iteration's with-skill runs with the reference score and cost.

Usage: python evals/compare.py ITERATION_DIR [--reference PATH]

For each case in the reference, reads ITERATION_DIR/<case>/with_skill/
grading.json and timing.json, adds the tokens of any subagents the run listed
in outputs/subagents.json, and prints the run beside the reference and the
no-skill arm. The no-skill arm is measured once per model and kept in the
reference, so an iteration need not rerun it. Exit 0 when every case scores
at least its reference and the run's extra tokens over the no-skill arm are
within max_extra_tokens, 1 when either fails, 2 when an input is missing or
malformed.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from grade import read_capped_text

DEFAULT_REFERENCE = Path(__file__).resolve().parent / "reference.json"
ARM = "with_skill"
SUBAGENTS = Path("outputs") / "subagents.json"


@dataclass(frozen=True, slots=True)
class Arm:
    passed: int
    tokens: int


@dataclass(frozen=True, slots=True)
class CaseReference:
    total: int
    with_skill: Arm
    without_skill: Arm


@dataclass(frozen=True, slots=True)
class Reference:
    max_extra_tokens: int
    cases: dict[str, CaseReference]


def _count(record: Mapping[str, object], name: str, where: object) -> int:
    value = record.get(name)
    # JSON true and false load as bool, which Python treats as an int.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"expected {name} in {where} to be a count, got {value!r}")
    return value


def _object(value: object, where: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"expected {where} to hold a JSON object, got {value!r}")
    return value


def _load(path: Path) -> object:
    return json.loads(read_capped_text(path))


def _arm(record: dict[str, object], name: str, where: str) -> Arm:
    arm = _object(record.get(name), f"{where} {name}")
    return Arm(_count(arm, "passed", where), _count(arm, "tokens", where))


def load_reference(path: Path) -> Reference:
    """Parse the reference file; raise ValueError on any malformed field."""
    document = _object(_load(path), path)
    cases = {}
    for name, value in _object(document.get("cases"), f"{path} cases").items():
        record = _object(value, f"case {name}")
        cases[name] = CaseReference(
            total=_count(record, "total", f"case {name}"),
            with_skill=_arm(record, "with_skill", f"case {name}"),
            without_skill=_arm(record, "without_skill", f"case {name}"),
        )
    if not cases:
        raise ValueError(f"{path} lists no cases")
    return Reference(_count(document, "max_extra_tokens", path), cases)


def _subagent_tokens(path: Path) -> int:
    if not path.is_file():
        return 0
    listed = _load(path)
    if not isinstance(listed, list):
        raise ValueError(f"expected {path} to hold a JSON list, got {listed!r}")
    return sum(_count(_object(item, path), "total_tokens", path) for item in listed)


def load_run(case_dir: Path, case: CaseReference) -> Arm:
    """Read one with-skill run's score and tokens, subagents included."""
    run = case_dir / ARM
    grading = _object(_load(run / "grading.json"), run / "grading.json")
    summary = _object(grading.get("summary"), f"{run} grading summary")
    total = _count(summary, "total", run)
    if total != case.total:
        raise ValueError(f"{run} has {total} expectations, reference has {case.total}")
    timing = _object(_load(run / "timing.json"), run / "timing.json")
    tokens = _count(timing, "total_tokens", run) + _subagent_tokens(run / SUBAGENTS)
    return Arm(_count(summary, "passed", run), tokens)


def failures(reference: Reference, runs: Mapping[str, Arm]) -> list[str]:
    """Name each case that scored below its reference, then any cost overrun."""
    found = [
        f"{name} scored {runs[name].passed} of {case.total}, "
        f"reference {case.with_skill.passed}"
        for name, case in reference.cases.items()
        if runs[name].passed < case.with_skill.passed
    ]
    extra = _extra_tokens(reference, runs)
    if extra > reference.max_extra_tokens:
        found.append(
            f"{extra} extra tokens over the {reference.max_extra_tokens} budget"
        )
    return found


def _extra_tokens(reference: Reference, runs: Mapping[str, Arm]) -> int:
    return sum(
        runs[name].tokens - case.without_skill.tokens
        for name, case in reference.cases.items()
    )


def _summed(arms: Iterable[Arm]) -> Arm:
    listed = list(arms)
    return Arm(sum(arm.passed for arm in listed), sum(arm.tokens for arm in listed))


def _row(name: str, width: int, total: int, arms: tuple[Arm, Arm, Arm]) -> str:
    scores = [f"{arm.passed}/{total}" for arm in arms]
    tokens = [str(arm.tokens) for arm in arms]
    return f"{name:<{width}}  " + "  ".join(f"{cell:>9}" for cell in scores + tokens)


def _table(reference: Reference, runs: Mapping[str, Arm]) -> list[str]:
    cases = reference.cases
    width = max(len(name) for name in [*cases, "total"])
    header = ("score", "reference", "no skill", "tokens", "reference", "no skill")
    lines = [f"{'case':<{width}}  " + "  ".join(f"{cell:>9}" for cell in header)]
    lines.extend(
        _row(name, width, case.total, (runs[name], case.with_skill, case.without_skill))
        for name, case in cases.items()
    )
    totals = (
        _summed(runs[name] for name in cases),
        _summed(case.with_skill for case in cases.values()),
        _summed(case.without_skill for case in cases.values()),
    )
    lines.append(_row("total", width, sum(c.total for c in cases.values()), totals))
    lines.append(
        f"extra tokens over no skill: {_extra_tokens(reference, runs)}"
        f" (budget {reference.max_extra_tokens})"
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare an eval iteration with the reference score and cost."
    )
    parser.add_argument("iteration", type=Path, help="the iteration directory")
    parser.add_argument(
        "--reference", type=Path, default=DEFAULT_REFERENCE, help="the reference"
    )
    args = parser.parse_args(argv)
    try:
        reference = load_reference(args.reference)
        runs = {
            name: load_run(args.iteration / name, case)
            for name, case in reference.cases.items()
        }
    except (OSError, ValueError) as err:
        print(f"cannot compare: {err}", file=sys.stderr)
        return 2
    print("\n".join(_table(reference, runs)))
    found = failures(reference, runs)
    for failure in found:
        print(f"FAIL: {failure}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
