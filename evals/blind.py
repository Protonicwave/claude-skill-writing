"""Hide which arm and model produced each eval run, so graders judge the text alone.

Usage:
  python evals/blind.py hide ITERATION_DIR --key KEY_PATH
  python evals/blind.py reveal ITERATION_DIR --key KEY_PATH

`hide` copies the outputs of every run under ITERATION_DIR/<model>/<case>/
<arm>/ to ITERATION_DIR/blind/<case>/<id>/, where the id is random, leaving
out subagents.json, and writes the key from id to run to KEY_PATH, which must
lie outside the iteration so a grader given the blind folder cannot read it.
Graders write grading.json into each copy. `reveal` then copies each grade to
its run's grading.json, and writes nothing unless every copy is graded.
Exit 0 on success, 2 when an input is missing or malformed.

Not hidden: what the text itself gives away, such as notes that mention the
skill's checker.
"""

import argparse
import json
import re
import secrets
import shutil
import sys
from pathlib import Path

BLIND = "blind"
OUTPUTS = "outputs"
GRADING = "grading.json"
LEFT_OUT = ("subagents.json",)
ID_DIGITS = 8
RUN_NAME = re.compile(r"with(out)?_skill(-\d+)?")
# A run as the key records it: <model>/<case>/<arm>, each part a plain name.
KEY_RUN = re.compile(r"[\w-][\w.-]*/[\w-][\w.-]*/with(out)?_skill(-\d+)?")


def find_runs(iteration: Path) -> list[Path]:
    """Every run directory of every model and case, relative to the iteration."""
    return sorted(
        path.relative_to(iteration)
        for path in iteration.glob("*/*/*")
        if RUN_NAME.fullmatch(path.name) and (path / OUTPUTS).is_dir()
    )


def hide(iteration: Path, key: Path) -> dict[str, str]:
    """Copy each run's outputs under a random id; return and save the key."""
    if key.resolve().is_relative_to(iteration.resolve()):
        raise ValueError(f"the key {key} must lie outside {iteration}")
    if not key.parent.is_dir():
        raise ValueError(f"the key's folder {key.parent} does not exist")
    if key.exists():
        raise ValueError(f"{key} already exists; reveal or remove the earlier round")
    blind = iteration / BLIND
    if blind.exists():
        raise ValueError(f"{blind} already exists; reveal or remove the earlier round")
    runs = find_runs(iteration)
    if not runs:
        raise ValueError(f"{iteration} holds no runs with outputs")
    # Sampling without replacement gives each run a distinct id.
    numbers = secrets.SystemRandom().sample(range(16**ID_DIGITS), len(runs))
    mapping: dict[str, str] = {}
    for run, number in zip(runs, numbers, strict=True):
        run_id = f"{number:0{ID_DIGITS}x}"
        mapping[run_id] = run.as_posix()
        shutil.copytree(
            iteration / run / OUTPUTS,
            blind / run.parts[1] / run_id,
            ignore=shutil.ignore_patterns(*LEFT_OUT),
        )
    key.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    return mapping


def _load_key(key: Path) -> dict[str, str]:
    mapping = json.loads(key.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict):
        raise ValueError(f"expected {key} to hold a JSON object")
    for run_id, run in mapping.items():
        if not isinstance(run, str) or not KEY_RUN.fullmatch(run):
            raise ValueError(f"expected {key} to map {run_id} to a run, got {run!r}")
    return mapping


def _grade(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"{path} is missing")
    text = path.read_text(encoding="utf-8")
    grading = json.loads(text)
    if not isinstance(grading, dict) or not isinstance(
        grading.get("expectations"), list
    ):
        raise ValueError(f"expected {path} to list expectations")
    return text


def reveal(iteration: Path, key: Path) -> int:
    """Copy every blind grade to its run; return the number copied."""
    grades = {
        run: _grade(iteration / BLIND / run.split("/")[1] / run_id / GRADING)
        for run_id, run in _load_key(key).items()
    }
    for run, text in grades.items():
        (iteration / run / GRADING).write_text(text, encoding="utf-8")
    return len(grades)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade eval runs blind.")
    parser.add_argument("command", choices=("hide", "reveal"))
    parser.add_argument("iteration", type=Path, help="the iteration directory")
    parser.add_argument(
        "--key", type=Path, required=True, help="the key, outside the iteration"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "hide":
            count = len(hide(args.iteration, args.key))
            print(f"{count} runs copied to {args.iteration / BLIND}")
        else:
            count = reveal(args.iteration, args.key)
            print(f"{count} grades copied back")
    except (OSError, ValueError) as err:
        print(f"cannot {args.command}: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover: entry point; main is tested directly
