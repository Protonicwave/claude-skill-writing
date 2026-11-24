"""Time verify.py with a cold cache on a fixed set of fifteen sources.

Usage:
  python evals/verify_timing.py [--runs N] [--max-seconds SECONDS]

Runs `verify.py -` on `verify_timing.jsonl` N times (default 3), each in a
fresh process reading standard input, so no cache is kept between runs, and
prints each run's seconds, the median and the budget. The default budget is
BUDGET_RATIO of SEQUENTIAL_SECONDS, the median measured when verify.py fetched
one source at a time. Exit 0 when the median is within the budget, 1 when it
is over, and 2 when a run fails to verify every source or passes its time
limit, since its time then measures a fault rather than the fetches.

Not measured: registry latency, which varies by hour. Compare figures taken
minutes apart.
"""

import argparse
import math
import subprocess
import sys
import time
from pathlib import Path
from statistics import median

EVALS = Path(__file__).resolve().parent
VERIFY = EVALS.parent / "writing" / "scripts" / "verify.py"
SOURCES = EVALS / "verify_timing.jsonl"
SEQUENTIAL_SECONDS = 7.4
# Crossref's public pool answers one request at a time, about 0.29 s each, so
# the fourteen DOIs here take 4.1 s however many other requests run alongside.
BUDGET_RATIO = 0.7
DEFAULT_RUNS = 3
RUN_TIMEOUT_SECONDS = 600.0


def time_run() -> float:
    """Seconds one cold run of verify.py takes; raises RuntimeError on a fault."""
    with SOURCES.open("rb") as sources:
        started = time.perf_counter()
        try:
            completed = subprocess.run(  # noqa: S603  fixed arguments, no shell
                [sys.executable, "-I", str(VERIFY), "-"],
                stdin=sources,
                capture_output=True,
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as err:
            raise RuntimeError(f"run passed {RUN_TIMEOUT_SECONDS:.0f} s") from err
        seconds = time.perf_counter() - started
    if completed.returncode != 0:
        tail = completed.stderr.decode("utf-8", "replace").strip()[-500:]
        raise RuntimeError(
            f"verify.py exited {completed.returncode}, not 0: {tail or 'no message'}"
        )
    return seconds


def _positive(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {text!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive number, got {text!r}")
    return value


def _run_count(text: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(
            f"expected a whole number of runs, got {text!r}"
        )
    return int(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Time verify.py with a cold cache against a budget."
    )
    parser.add_argument("--runs", type=_run_count, default=DEFAULT_RUNS)
    parser.add_argument(
        "--max-seconds",
        type=_positive,
        default=BUDGET_RATIO * SEQUENTIAL_SECONDS,
        help="the budget for the median run",
    )
    args = parser.parse_args(argv)
    seconds: list[float] = []
    for number in range(1, args.runs + 1):
        try:
            seconds.append(time_run())
        except RuntimeError as err:
            print(f"verify_timing.py: run {number}: {err}", file=sys.stderr)
            return 2
        print(f"run {number}: {seconds[-1]:.1f} s")
    middle = median(seconds)
    verdict = "within" if middle <= args.max_seconds else "over"
    print(f"median {middle:.1f} s, budget {args.max_seconds:.1f} s: {verdict}")
    return 0 if verdict == "within" else 1


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover: entry point; main is tested directly
