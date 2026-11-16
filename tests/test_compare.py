import json
from pathlib import Path

import pytest
from compare import main

# Per case: with-skill passed, total, with-skill tokens, no-skill passed and tokens.
CASES = {"first-case": (6, 7, 1000, 5, 400), "second-case": (3, 3, 800, 3, 500)}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_reference(tmp_path: Path, max_extra_tokens: int) -> Path:
    path = tmp_path / "reference.json"
    cases = {
        name: {
            "total": total,
            "with_skill": {"passed": passed, "tokens": tokens},
            "without_skill": {"passed": base_passed, "tokens": base_tokens},
        }
        for name, (passed, total, tokens, base_passed, base_tokens) in CASES.items()
    }
    write_json(path, {"max_extra_tokens": max_extra_tokens, "cases": cases})
    return path


def write_run(iteration: Path, name: str, passed: int, total: int, tokens: int) -> Path:
    run = iteration / name / "with_skill"
    summary = {"passed": passed, "failed": total - passed, "total": total}
    write_json(run / "grading.json", {"expectations": [], "summary": summary})
    write_json(run / "timing.json", {"total_tokens": tokens})
    return run


def write_iteration(tmp_path: Path) -> Path:
    """An iteration that scores and costs exactly what the reference records."""
    iteration = tmp_path / "iteration-1"
    for name, (passed, total, tokens, _, _) in CASES.items():
        write_run(iteration, name, passed, total, tokens)
    return iteration


def run_main(iteration: Path, reference: Path) -> int:
    return main([str(iteration), "--reference", str(reference)])


# Reference extra tokens: (1000 + 800) - (400 + 500) = 900.
def test_passes_on_a_run_equal_to_the_reference(tmp_path: Path) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=900)
    assert run_main(write_iteration(tmp_path), reference) == 0


def test_passes_when_a_case_scores_above_its_reference(tmp_path: Path) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=900)
    iteration = write_iteration(tmp_path)
    write_run(iteration, "first-case", 7, 7, 1000)
    assert run_main(iteration, reference) == 0


def test_fails_on_a_one_point_drop_in_one_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=900)
    iteration = write_iteration(tmp_path)
    write_run(iteration, "second-case", 2, 3, 800)
    assert run_main(iteration, reference) == 1
    assert "second-case scored 2 of 3, reference 3" in capsys.readouterr().out


def test_fails_when_extra_tokens_exceed_the_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=899)
    assert run_main(write_iteration(tmp_path), reference) == 1
    assert "900 extra tokens over the 899 budget" in capsys.readouterr().out


def test_counts_the_tokens_of_listed_subagents(tmp_path: Path) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=900)
    iteration = write_iteration(tmp_path)
    write_json(
        iteration / "first-case" / "with_skill" / "outputs" / "subagents.json",
        [{"purpose": "cold read", "total_tokens": 1}],
    )
    assert run_main(iteration, reference) == 1


@pytest.mark.parametrize(
    "missing",
    ["second-case", "second-case/with_skill", "second-case/with_skill/timing.json"],
)
def test_exits_2_naming_a_missing_case_or_arm(
    tmp_path: Path, missing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=900)
    iteration = write_iteration(tmp_path)
    target = iteration / missing
    if target.is_file():
        target.unlink()
    else:
        for path in sorted(target.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        target.rmdir()
    assert run_main(iteration, reference) == 2
    assert "second-case" in capsys.readouterr().err


def test_exits_2_when_the_expectation_count_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=900)
    iteration = write_iteration(tmp_path)
    write_run(iteration, "first-case", 6, 8, 1000)
    assert run_main(iteration, reference) == 2
    assert "8 expectations, reference has 7" in capsys.readouterr().err


@pytest.mark.parametrize(
    "subagents",
    [{"total_tokens": 5}, [{"purpose": "review"}], [{"total_tokens": -1}]],
)
def test_exits_2_on_a_malformed_subagent_list(
    tmp_path: Path, subagents: object
) -> None:
    reference = write_reference(tmp_path, max_extra_tokens=900)
    iteration = write_iteration(tmp_path)
    write_json(
        iteration / "first-case" / "with_skill" / "outputs" / "subagents.json",
        subagents,
    )
    assert run_main(iteration, reference) == 2


def test_exits_2_on_a_malformed_reference(tmp_path: Path) -> None:
    reference = tmp_path / "reference.json"
    write_json(reference, {"max_extra_tokens": "many", "cases": {}})
    assert run_main(write_iteration(tmp_path), reference) == 2


def test_shipped_reference_names_every_case_in_the_eval_set() -> None:
    evals_dir = Path(__file__).resolve().parent.parent / "evals"
    reference = json.loads((evals_dir / "reference.json").read_text(encoding="utf-8"))
    evals = json.loads((evals_dir / "evals.json").read_text(encoding="utf-8"))
    assert len(reference["cases"]) == len(evals["evals"])
