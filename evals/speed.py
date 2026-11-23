"""Compare two arms of an eval on score, spend and wall time, case by case.

Usage:
  python evals/speed.py ITERATION --model MODEL --arm ARM --against ARM
      [--baseline-iteration DIR] [--max-seconds-ratio RATIO] [--case NAME ...]
      [--reference PATH]

For every case that has a run of either arm, or each case named with --case,
prints the median score, the median spend and the median wall time of each
arm's runs (an arm's repeats sit in ARM, ARM-2, ARM-3). A run's wall time is
the span from the earliest to the latest timestamp across its transcript and
its subagents' transcripts. Exit 0 when the summed wall time is at most RATIO
of the baseline's (default 1), the summed spend is no higher and no case scores
lower; exit 1 otherwise, naming each miss; exit 2 when a run, a transcript, a
timestamp, a grade or a price is missing or malformed, or a case has runs of
one arm only.

Not measured: load on the machine. Launch both arms in one batch so it affects
them alike.
"""

import argparse
import glob
import json
import math
import re
import sys
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median

from spend import (
    DEFAULT_REFERENCE,
    MAX_TRANSCRIPT_BYTES,
    TRANSCRIPTS,
    Prices,
    load_prices,
    run_spend,
)

DEFAULT_MAX_SECONDS_RATIO = 1.0


@dataclass(frozen=True, slots=True)
class Figures:
    passed: float
    spend: float
    seconds: float


Cases = dict[str, tuple[Figures, Figures]]


def _object(value: object, where: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"expected {where} to be a JSON object, got {value!r}")
    return value


def _timestamps(path: Path) -> Iterator[datetime]:
    if path.stat().st_size > MAX_TRANSCRIPT_BYTES:
        raise ValueError(f"{path} is over {MAX_TRANSCRIPT_BYTES} bytes")
    with path.open(encoding="utf-8") as lines:
        for number, line in enumerate(lines, start=1):
            where = f"{path}:{number}"
            try:
                entry = _object(json.loads(line), where)
            except json.JSONDecodeError as err:
                raise ValueError(f"{where} is not JSON: {err}") from err
            if "timestamp" not in entry:
                continue
            text = entry["timestamp"]
            try:
                moment = datetime.fromisoformat(str(text))
            except ValueError as err:
                raise ValueError(f"{where} has timestamp {text!r}: {err}") from err
            if moment.tzinfo is None:
                raise ValueError(f"{where} has timestamp {text!r} with no zone")
            yield moment


def wall_seconds(run: Path) -> float:
    """Seconds from the first to the last timestamp across a run's transcripts."""
    directory = run / TRANSCRIPTS
    paths = sorted(directory.glob("agent-*.jsonl")) if directory.is_dir() else []
    if not paths:
        raise ValueError(f"{directory} holds no transcripts")
    moments = [moment for path in paths for moment in _timestamps(path)]
    if not moments:
        raise ValueError(f"{run} has no timestamps in its transcripts")
    seconds = (max(moments) - min(moments)).total_seconds()
    if seconds <= 0:
        raise ValueError(f"the timestamps of {run} span no time")
    return seconds


def _passed(run: Path) -> int:
    path = run / "grading.json"
    grading = _object(json.loads(path.read_text(encoding="utf-8")), path)
    summary = _object(grading.get("summary"), f"the summary of {path}")
    passed = summary.get("passed")
    # JSON true and false load as bool, which Python treats as an int.
    if isinstance(passed, bool) or not isinstance(passed, int) or passed < 0:
        raise ValueError(f"expected passed in {path} to be a count, got {passed!r}")
    return passed


def _runs(case_dir: Path, arm: str) -> list[Path]:
    name = re.compile(rf"{re.escape(arm)}(-\d+)?")
    return sorted(
        path
        for path in case_dir.glob(f"{glob.escape(arm)}*")
        if path.is_dir() and name.fullmatch(path.name)
    )


def _figures(runs: list[Path], prices: Prices) -> Figures:
    seconds = median(wall_seconds(run) for run in runs)
    return Figures(
        median(_passed(run) for run in runs),
        median(run_spend(run, prices) for run in runs),
        seconds,
    )


@dataclass(frozen=True, slots=True)
class Arm:
    """An arm's runs: `name`, `name-2` and so on in each case under `model_dir`."""

    model_dir: Path
    name: str

    def cases(self) -> set[str]:
        return {path.name for path in self.model_dir.iterdir() if self.runs(path.name)}

    def runs(self, case: str) -> list[Path]:
        return _runs(self.model_dir / case, self.name)


def load_arms(
    new: Arm, baseline: Arm, prices: Prices, only: Collection[str] = ()
) -> Cases:
    """Each case's baseline and new figures, for the cases in `only` if any.

    Raises ValueError if a case lacks an arm.
    """
    found = {arm: arm.cases() for arm in (new, baseline)}
    wanted = set(only) or found[new] | found[baseline]
    for name in sorted(wanted):
        for arm in (new, baseline):
            if name not in found[arm]:
                raise ValueError(
                    f"case {name} has no {arm.name} run in {arm.model_dir}"
                )
    if not wanted:
        raise ValueError(f"no case has a {new.name} or {baseline.name} run")
    return {
        name: (_figures(baseline.runs(name), prices), _figures(new.runs(name), prices))
        for name in sorted(wanted)
    }


def _totals(cases: Cases) -> tuple[Figures, Figures]:
    def total(figures: list[Figures]) -> Figures:
        return Figures(
            sum(f.passed for f in figures),
            sum(f.spend for f in figures),
            sum(f.seconds for f in figures),
        )

    return (
        total([old for old, _ in cases.values()]),
        total([new for _, new in cases.values()]),
    )


def failures(cases: Cases, max_seconds_ratio: float) -> list[str]:
    """Name each case that scores lower, then the spend or time budget missed."""
    found = [
        f"{name} scored {new.passed:g}, baseline {old.passed:g}"
        for name, (old, new) in cases.items()
        if new.passed < old.passed
    ]
    old_total, new_total = _totals(cases)
    if new_total.spend > old_total.spend:
        found.append(f"spend ${new_total.spend:.2f} is above ${old_total.spend:.2f}")
    if new_total.seconds > max_seconds_ratio * old_total.seconds:
        found.append(
            f"seconds {new_total.seconds:.0f}s are "
            f"{new_total.seconds / old_total.seconds:.2f} of "
            f"{old_total.seconds:.0f}s, over the {max_seconds_ratio:.2f} budget"
        )
    return found


def _row(name: str, width: int, old: Figures, new: Figures) -> str:
    cells = [
        f"{old.passed:g}",
        f"{new.passed:g}",
        f"${old.spend:.2f}",
        f"${new.spend:.2f}",
        f"{old.seconds:.0f}s",
        f"{new.seconds:.0f}s",
    ]
    return f"{name:<{width}}  " + "  ".join(f"{cell:>9}" for cell in cells)


def _table(cases: Cases, max_seconds_ratio: float) -> list[str]:
    width = max(len(name) for name in [*cases, "total"])
    header = ("score", "new", "spend", "new", "seconds", "new")
    lines = [f"{'case':<{width}}  " + "  ".join(f"{cell:>9}" for cell in header)]
    lines.extend(_row(name, width, old, new) for name, (old, new) in cases.items())
    old_total, new_total = _totals(cases)
    lines.append(_row("total", width, old_total, new_total))
    lines.append(
        f"seconds ratio {new_total.seconds / old_total.seconds:.2f} "
        f"against budget {max_seconds_ratio:.2f}"
    )
    return lines


def _positive_ratio(text: str) -> float:
    try:
        ratio = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {text!r}") from None
    if not math.isfinite(ratio) or ratio <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive ratio, got {text!r}")
    return ratio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare two eval arms on score, spend and wall time."
    )
    parser.add_argument("iteration", type=Path, help="the iteration directory")
    parser.add_argument("--model", required=True, help="the model's folder")
    parser.add_argument("--arm", required=True, help="the arm under test")
    parser.add_argument("--against", required=True, help="the baseline arm")
    parser.add_argument(
        "--baseline-iteration",
        type=Path,
        help="the iteration holding the baseline arm, if not the same",
    )
    parser.add_argument(
        "--max-seconds-ratio",
        type=_positive_ratio,
        default=DEFAULT_MAX_SECONDS_RATIO,
        help="the most wall time the arm may take, as a share of the baseline's",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        dest="cases",
        help="compare only this case; repeat for more",
    )
    parser.add_argument(
        "--reference", type=Path, default=DEFAULT_REFERENCE, help="the price table"
    )
    args = parser.parse_args(argv)
    baseline_iteration = args.baseline_iteration or args.iteration
    try:
        cases = load_arms(
            Arm(args.iteration / args.model, args.arm),
            Arm(baseline_iteration / args.model, args.against),
            load_prices(args.reference),
            args.cases,
        )
    except (OSError, ValueError) as err:
        print(f"cannot compare: {err}", file=sys.stderr)
        return 2
    print("\n".join(_table(cases, args.max_seconds_ratio)))
    found = failures(cases, args.max_seconds_ratio)
    for failure in found:
        print(f"FAIL: {failure}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover: entry point; main is tested directly
