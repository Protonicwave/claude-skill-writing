"""Compare an eval iteration's with-skill runs with the reference for one model.

Usage: python evals/compare.py ITERATION_DIR --model MODEL [--reference PATH]
                               [--against deep_research]

For each case in the model's section of the reference, reads every run under
ITERATION_DIR/<model>/<case>/: with_skill/, and with_skill-2/ and so on for
a case run more than once. A run's score comes from its grading.json and its
spend from its captured transcripts, subagents included (see spend.py). Where
a case has several runs, the median of each figure counts. The no-skill arm
is measured once per model and kept in the reference.

With --against deep_research the run instead compares, on each case the
model's deep_research entry lists, the median with_skill figures with the
median of the deep_research/, deep_research-2/ and later runs of the same
iteration. It fails when the skill scores below deep research or spends no
less on any case, and when the gap search's extra spend (the skill's median
spend on the budget case less its baseline_usd) exceeds max_share_of_rival of
deep research's median spend on that case.

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
DEEP_RESEARCH = "deep_research"


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
class GapSearchBudget:
    case: str
    baseline_usd: float
    max_share_of_rival: float


@dataclass(frozen=True, slots=True)
class DeepResearch:
    cases: tuple[str, ...]
    budget: GapSearchBudget


@dataclass(frozen=True, slots=True)
class ModelReference:
    cases: dict[str, CaseReference]
    budget: SpendBudget | None
    rival: str | None
    deep_research: DeepResearch | None


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


def _deep_research(
    section: dict[str, object], model: str, listed: set[str]
) -> DeepResearch | None:
    if DEEP_RESEARCH not in section:
        return None
    where = f"{model} {DEEP_RESEARCH}"
    record = _object(section[DEEP_RESEARCH], where)
    cases = record.get("cases")
    if not isinstance(cases, list) or not all(isinstance(c, str) for c in cases):
        raise ValueError(f"expected {where} to list case names")
    if not cases or not set(cases) <= listed:
        raise ValueError(f"{where} names a case the section does not list")
    spend = _object(record.get("gap_search_budget"), f"{where} gap_search_budget")
    case = spend.get("case")
    if case not in cases:
        raise ValueError(f"{where} gap_search_budget names a case it does not compare")
    budget = GapSearchBudget(
        str(case),
        _number(spend, "baseline_usd", f"{where} gap_search_budget"),
        _number(spend, "max_share_of_rival", f"{where} gap_search_budget"),
    )
    if not 0 < budget.max_share_of_rival <= 1:
        raise ValueError(
            f"expected {where} max_share_of_rival in (0, 1], "
            f"got {budget.max_share_of_rival:g}"
        )
    return DeepResearch(tuple(cases), budget)


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
    return ModelReference(
        cases, budget, rival, _deep_research(section, model, set(cases))
    )


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


def load_case(
    case_dir: Path, case: CaseReference, prices: Prices, arm: str = "with_skill"
) -> Figures:
    """The median score and spend of a case's runs of one arm, repeats included."""
    name = re.compile(rf"{arm}(-\d+)?")
    runs = sorted(
        path
        for path in case_dir.glob(f"{arm}*")
        if path.is_dir() and name.fullmatch(path.name)
    )
    if not runs:
        raise ValueError(f"{case_dir} has no {arm} run")
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


def _gap_search_spend(
    budget: GapSearchBudget,
    skill: Mapping[str, Figures],
    deep_runs: Mapping[str, Figures],
) -> tuple[float, float]:
    """The skill's spend over its baseline on the budget case, and the limit."""
    return (
        skill[budget.case].spend - budget.baseline_usd,
        budget.max_share_of_rival * deep_runs[budget.case].spend,
    )


def against_failures(
    entry: DeepResearch,
    skill: Mapping[str, Figures],
    deep_runs: Mapping[str, Figures],
    totals: Mapping[str, int],
) -> list[str]:
    """Name each case the skill scores below or spends no less on, then the budget."""
    found = []
    for name in entry.cases:
        if skill[name].passed < deep_runs[name].passed:
            found.append(
                f"{name} scored {skill[name].passed:g} of {totals[name]}, "
                f"deep research {deep_runs[name].passed:g}"
            )
        if skill[name].spend >= deep_runs[name].spend:
            found.append(
                f"{name} spent ${skill[name].spend:.2f}, not below "
                f"deep research's ${deep_runs[name].spend:.2f}"
            )
    extra, limit = _gap_search_spend(entry.budget, skill, deep_runs)
    if extra > limit:
        found.append(
            f"${extra:.2f} gap search spend over the ${limit:.2f} budget "
            f"on {entry.budget.case}"
        )
    return found


def _against_table(
    entry: DeepResearch,
    totals: Mapping[str, int],
    skill: Mapping[str, Figures],
    deep_runs: Mapping[str, Figures],
) -> list[str]:
    width = max(len(name) for name in [*entry.cases, "case"])
    header = ("score", "deep res.", "spend", "deep res.")
    lines = [f"{'case':<{width}}  " + "  ".join(f"{cell:>9}" for cell in header)]
    lines.extend(
        _row(name, width, totals[name], (skill[name], deep_runs[name]))
        for name in entry.cases
    )
    extra, limit = _gap_search_spend(entry.budget, skill, deep_runs)
    lines.append(
        f"gap search spend on {entry.budget.case}: ${extra:.2f} "
        f"(budget ${limit:.2f}, {entry.budget.max_share_of_rival:.0%} "
        f"of deep research's ${deep_runs[entry.budget.case].spend:.2f})"
    )
    return lines


def _compare_with_deep_research(
    iteration: Path, model: str, models: Mapping[str, ModelReference], prices: Prices
) -> int:
    reference = models[model]
    entry = reference.deep_research
    if entry is None:
        raise ValueError(f"{model} has no {DEEP_RESEARCH} entry in the reference")
    skill = {}
    deep_runs = {}
    for name in entry.cases:
        case_dir = iteration / model / name
        skill[name] = load_case(case_dir, reference.cases[name], prices)
        deep_runs[name] = load_case(
            case_dir, reference.cases[name], prices, DEEP_RESEARCH
        )
    totals = {name: reference.cases[name].total for name in entry.cases}
    print("\n".join(_against_table(entry, totals, skill, deep_runs)))
    found = against_failures(entry, skill, deep_runs, totals)
    for failure in found:
        print(f"FAIL: {failure}")
    return 1 if found else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare an eval iteration with the reference for one model."
    )
    parser.add_argument("iteration", type=Path, help="the iteration directory")
    parser.add_argument("--model", required=True, help="the reference section")
    parser.add_argument(
        "--reference", type=Path, default=DEFAULT_REFERENCE, help="the reference"
    )
    parser.add_argument(
        "--against",
        choices=(DEEP_RESEARCH,),
        help="compare with the deep-research runs of the same iteration instead",
    )
    args = parser.parse_args(argv)
    try:
        models = load_reference(args.reference)
        if args.model not in models:
            raise ValueError(f"{args.reference} has no section for {args.model}")
        prices = load_prices(args.reference)
        if args.against:
            return _compare_with_deep_research(
                args.iteration, args.model, models, prices
            )
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
