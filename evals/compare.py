"""Compare an eval iteration's with-skill runs with the reference for one model.

Usage: python evals/compare.py ITERATION_DIR --model MODEL [--reference PATH]

For each case in the model's section of the reference, reads every run under
ITERATION_DIR/<model>/<case>/: with_skill/, and with_skill-2/ and so on for
a case run more than once. A run's score comes from its grading.json and its
spend from its captured transcripts, subagents included (see spend.py). Where
a case has several runs, the median of each figure counts. The no-skill arm
is measured once per model and kept in the reference.

The run fails when a case scores below its reference, when the total score
does not beat the model's own no-skill arm, when the extra spend over that arm
on the budgeted cases exceeds max_extra_spend, or, for a section that names a
rival, when the total score is below the rival's no-skill arm or the total
spend is not below it. Exit 0 on a pass, 1 on a failure, 2 when an input is
missing or malformed.
"""

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from grade import read_capped_text
from spend import Prices, load_prices, run_spend

DEFAULT_REFERENCE = Path(__file__).resolve().parent / "reference.json"
# The first run of a case, then its repeats.
RUN_NAME = re.compile(r"with_skill(-\d+)?")


@dataclass(frozen=True, slots=True)
class Figures:
    passed: float
    spend: float


@dataclass(frozen=True, slots=True)
class CaseReference:
    total: int
    with_skill: Figures
    without_skill: Figures


@dataclass(frozen=True, slots=True)
class SpendBudget:
    usd: float
    cases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelReference:
    cases: dict[str, CaseReference]
    budget: SpendBudget | None
    rival: str | None


def _object(value: object, where: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"expected {where} to hold a JSON object, got {value!r}")
    return value


def _number(record: Mapping[str, object], name: str, where: object) -> float:
    value = record.get(name)
    # JSON true and false load as bool, which Python treats as an int.
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError(f"expected {name} in {where} to be a figure, got {value!r}")
    return float(value)


def _count(record: Mapping[str, object], name: str, where: object) -> int:
    value = _number(record, name, where)
    if not value.is_integer():
        raise ValueError(f"expected {name} in {where} to be a count, got {value!r}")
    return int(value)


def _load(path: Path) -> object:
    return json.loads(read_capped_text(path))


def _figures(record: dict[str, object], name: str, where: str) -> Figures:
    where = f"{where} {name}"
    arm = _object(record.get(name), where)
    return Figures(_number(arm, "passed", where), _number(arm, "spend_usd", where))


def _case(name: str, value: object, model: str) -> CaseReference:
    where = f"{model} case {name}"
    record = _object(value, where)
    return CaseReference(
        total=_count(record, "total", where),
        with_skill=_figures(record, "with_skill", where),
        without_skill=_figures(record, "without_skill", where),
    )


def _budget(section: dict[str, object], model: str) -> SpendBudget | None:
    if "max_extra_spend" not in section:
        return None
    record = _object(section["max_extra_spend"], f"{model} max_extra_spend")
    cases = record.get("cases")
    if not isinstance(cases, list) or not all(isinstance(c, str) for c in cases):
        raise ValueError(f"expected {model} max_extra_spend to list case names")
    return SpendBudget(_number(record, "usd", f"{model} max_extra_spend"), tuple(cases))


def _model(model: str, value: object) -> ModelReference:
    section = _object(value, f"model {model}")
    cases = {
        name: _case(name, record, model)
        for name, record in _object(section.get("cases"), f"{model} cases").items()
    }
    if not cases:
        raise ValueError(f"{model} lists no cases")
    budget = _budget(section, model)
    if budget is not None and not set(budget.cases) <= set(cases):
        raise ValueError(f"{model} max_extra_spend names a case it does not list")
    rival = section.get("rival")
    if rival is not None and not isinstance(rival, str):
        raise ValueError(f"expected {model} rival to name a model, got {rival!r}")
    return ModelReference(cases, budget, rival)


def load_reference(path: Path) -> dict[str, ModelReference]:
    """Parse every model's section; raise ValueError on any malformed field."""
    document = _object(_load(path), path)
    models = {
        model: _model(model, value)
        for model, value in _object(document.get("models"), f"{path} models").items()
    }
    for model, section in models.items():
        if section.rival is None:
            continue
        if section.rival not in models:
            raise ValueError(
                f"{model} names rival {section.rival}, which has no section"
            )
        if set(models[section.rival].cases) != set(section.cases):
            raise ValueError(
                f"{model} and its rival {section.rival} list different cases"
            )
    return models


def _run(run: Path, case: CaseReference, prices: Prices) -> Figures:
    grading = _object(_load(run / "grading.json"), run / "grading.json")
    summary = _object(grading.get("summary"), f"{run} grading summary")
    total = _count(summary, "total", run)
    if total != case.total:
        raise ValueError(f"{run} has {total} expectations, reference has {case.total}")
    return Figures(_count(summary, "passed", run), run_spend(run, prices))


def load_case(case_dir: Path, case: CaseReference, prices: Prices) -> Figures:
    """The median score and spend of a case's with-skill runs."""
    runs = sorted(
        path
        for path in case_dir.glob("with_skill*")
        if path.is_dir() and RUN_NAME.fullmatch(path.name)
    )
    if not runs:
        raise ValueError(f"{case_dir} has no with_skill run")
    figures = [_run(run, case, prices) for run in runs]
    return Figures(
        median(item.passed for item in figures), median(item.spend for item in figures)
    )


def _summed(figures: Iterable[Figures]) -> Figures:
    listed = list(figures)
    return Figures(sum(f.passed for f in listed), sum(f.spend for f in listed))


def _extra_spend(
    section: ModelReference, budget: SpendBudget, runs: Mapping[str, Figures]
) -> float:
    return sum(
        runs[name].spend - section.cases[name].without_skill.spend
        for name in budget.cases
    )


def failures(
    models: Mapping[str, ModelReference], model: str, runs: Mapping[str, Figures]
) -> list[str]:
    """Name each case below its reference, then each total or budget the runs miss."""
    section = models[model]
    found = [
        f"{name} scored {runs[name].passed:g} of {case.total}, "
        f"reference {case.with_skill.passed:g}"
        for name, case in section.cases.items()
        if runs[name].passed < case.with_skill.passed
    ]
    run_total = _summed(runs.values())
    plain = _summed(case.without_skill for case in section.cases.values())
    if run_total.passed <= plain.passed:
        found.append(
            f"total score {run_total.passed:g} does not beat "
            f"{plain.passed:g} without the skill"
        )
    if section.budget is not None:
        extra = _extra_spend(section, section.budget, runs)
        if extra > section.budget.usd:
            found.append(
                f"${extra:.2f} extra spend over the ${section.budget.usd:.2f} budget"
            )
    if section.rival is not None:
        rival = _summed(
            case.without_skill for case in models[section.rival].cases.values()
        )
        if run_total.passed < rival.passed:
            found.append(
                f"total score {run_total.passed:g} is below plain "
                f"{section.rival}'s {rival.passed:g}"
            )
        if run_total.spend >= rival.spend:
            found.append(
                f"spend ${run_total.spend:.2f} is not below plain "
                f"{section.rival}'s ${rival.spend:.2f}"
            )
    return found


def _row(name: str, width: int, total: int, arms: tuple[Figures, ...]) -> str:
    scores = [f"{arm.passed:g}/{total}" for arm in arms]
    spends = [f"${arm.spend:.2f}" for arm in arms]
    return f"{name:<{width}}  " + "  ".join(f"{cell:>9}" for cell in scores + spends)


def _table(section: ModelReference, runs: Mapping[str, Figures]) -> list[str]:
    cases = section.cases
    width = max(len(name) for name in [*cases, "total"])
    header = ("score", "reference", "no skill", "spend", "reference", "no skill")
    lines = [f"{'case':<{width}}  " + "  ".join(f"{cell:>9}" for cell in header)]
    lines.extend(
        _row(name, width, case.total, (runs[name], case.with_skill, case.without_skill))
        for name, case in cases.items()
    )
    totals = (
        _summed(runs.values()),
        _summed(case.with_skill for case in cases.values()),
        _summed(case.without_skill for case in cases.values()),
    )
    lines.append(_row("total", width, sum(c.total for c in cases.values()), totals))
    if section.budget is not None:
        budget = section.budget
        lines.append(
            f"extra spend over no skill on {len(budget.cases)} cases: "
            f"${_extra_spend(section, budget, runs):.2f} (budget ${budget.usd:.2f})"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare an eval iteration with the reference for one model."
    )
    parser.add_argument("iteration", type=Path, help="the iteration directory")
    parser.add_argument("--model", required=True, help="the reference section")
    parser.add_argument(
        "--reference", type=Path, default=DEFAULT_REFERENCE, help="the reference"
    )
    args = parser.parse_args(argv)
    try:
        models = load_reference(args.reference)
        if args.model not in models:
            raise ValueError(f"{args.reference} has no section for {args.model}")
        prices = load_prices(args.reference)
        section = models[args.model]
        runs = {
            name: load_case(args.iteration / args.model / name, case, prices)
            for name, case in section.cases.items()
        }
    except (OSError, ValueError) as err:
        print(f"cannot compare: {err}", file=sys.stderr)
        return 2
    print("\n".join(_table(section, runs)))
    found = failures(models, args.model, runs)
    for failure in found:
        print(f"FAIL: {failure}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover: entry point; main is tested directly
