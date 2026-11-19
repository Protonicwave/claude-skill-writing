import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from compare import main

# Per model and case: total, with-skill passed and spend, no-skill passed and spend.
FIGURES = {
    "opus": {"first-case": (7, 6, 10, 5, 4), "second-case": (3, 3, 8, 2, 5)},
    "sonnet": {"first-case": (7, 5, 6, 3, 2), "second-case": (3, 3, 2, 1, 1)},
}
# Opus's extra spend over its no-skill arm: (10 - 4) + (8 - 5) = 9.
OPUS_BUDGET = 9
# A dollar per input token, so a run's spend is the token count its transcript gives.
PRICES = {
    "date": "2026-11-19",
    "usd_per_million_tokens": {
        "model-a": {
            "input": 1_000_000,
            "output": 0,
            "cache_write_5m": 0,
            "cache_write_1h": 0,
            "cache_read": 0,
        }
    },
}


# The reference as loaded JSON, which the tests reshape before writing.
Document = dict[str, Any]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def reference_document() -> Document:
    models: Document = {
        model: {
            "cases": {
                name: {
                    "total": total,
                    "with_skill": {"passed": passed, "spend_usd": spend},
                    "without_skill": {"passed": base_passed, "spend_usd": base_spend},
                }
                for name, (
                    total,
                    passed,
                    spend,
                    base_passed,
                    base_spend,
                ) in cases.items()
            }
        }
        for model, cases in FIGURES.items()
    }
    models["opus"]["max_extra_spend"] = {
        "usd": OPUS_BUDGET,
        "cases": ["first-case", "second-case"],
    }
    models["sonnet"]["rival"] = "opus"
    return {"prices": PRICES, "models": models}


def write_reference(tmp_path: Path, document: object = None) -> Path:
    path = tmp_path / "reference.json"
    write_json(path, reference_document() if document is None else document)
    return path


def write_run(
    case_dir: Path, passed: int, total: int, spend: int, name: str = "with_skill"
) -> Path:
    run = case_dir / name
    summary = {"passed": passed, "failed": total - passed, "total": total}
    write_json(run / "grading.json", {"expectations": [], "summary": summary})
    message = {
        "id": f"{case_dir.name}-{name}",
        "model": "model-a",
        "usage": {
            "input_tokens": spend,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 0,
                "ephemeral_1h_input_tokens": 0,
            },
        },
    }
    transcript = run / "transcripts" / "agent-r1.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    entry = {"type": "assistant", "message": message}
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return run


def write_iteration(tmp_path: Path) -> Path:
    """An iteration that scores and spends exactly what the reference records."""
    iteration = tmp_path / "iteration-1"
    for model, cases in FIGURES.items():
        for name, (total, passed, spend, _, _) in cases.items():
            write_run(iteration / model / name, passed, total, spend)
    return iteration


def run_main(iteration: Path, reference: Path, model: str = "opus") -> int:
    return main([str(iteration), "--model", model, "--reference", str(reference)])


@pytest.mark.parametrize("model", ["opus", "sonnet"])
def test_passes_on_a_run_equal_to_the_reference(tmp_path: Path, model: str) -> None:
    assert run_main(write_iteration(tmp_path), write_reference(tmp_path), model) == 0


def test_passes_when_a_case_scores_above_its_reference(tmp_path: Path) -> None:
    iteration = write_iteration(tmp_path)
    write_run(iteration / "opus" / "first-case", 7, 7, 10)
    assert run_main(iteration, write_reference(tmp_path)) == 0


def test_fails_on_a_one_point_drop_in_one_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    write_run(iteration / "opus" / "second-case", 2, 3, 8)
    assert run_main(iteration, write_reference(tmp_path)) == 1
    assert "second-case scored 2 of 3, reference 3" in capsys.readouterr().out


def test_fails_when_extra_spend_exceeds_the_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    write_run(iteration / "opus" / "first-case", 6, 7, 11)
    assert run_main(iteration, write_reference(tmp_path)) == 1
    assert "$10.00 extra spend over the $9.00 budget" in capsys.readouterr().out


def test_counts_extra_spend_only_on_the_budgeted_cases(tmp_path: Path) -> None:
    document = reference_document()
    document["models"]["opus"]["max_extra_spend"] = {"usd": 6, "cases": ["first-case"]}
    iteration = write_iteration(tmp_path)
    write_run(iteration / "opus" / "second-case", 3, 3, 50)
    assert run_main(iteration, write_reference(tmp_path, document)) == 0


def test_counts_the_spend_of_spawned_subagents(tmp_path: Path) -> None:
    iteration = write_iteration(tmp_path)
    transcripts = iteration / "opus" / "first-case" / "with_skill" / "transcripts"
    child = json.loads((transcripts / "agent-r1.jsonl").read_text(encoding="utf-8"))
    child["message"]["id"] = "child-message"
    child["message"]["usage"]["input_tokens"] = 1
    write_json(transcripts / "agent-r2.jsonl", child)
    with (transcripts / "agent-r1.jsonl").open("a", encoding="utf-8") as root:
        root.write(json.dumps({"toolUseResult": {"agentId": "r2"}}) + "\n")
    assert run_main(iteration, write_reference(tmp_path)) == 1


def test_takes_the_median_of_repeated_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    case_dir = iteration / "opus" / "first-case"
    write_run(case_dir, 7, 7, 12, name="with_skill-2")
    assert run_main(iteration, write_reference(tmp_path)) == 1
    output = capsys.readouterr().out
    assert "6.5/7" in output
    assert "$10.00 extra spend over the $9.00 budget" in output


def test_fails_when_the_skill_does_not_beat_its_own_model_without_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = reference_document()
    document["models"]["opus"]["cases"]["first-case"]["with_skill"]["passed"] = 3
    iteration = write_iteration(tmp_path)
    write_run(iteration / "opus" / "first-case", 3, 7, 10)
    assert run_main(iteration, write_reference(tmp_path, document)) == 1
    assert "total score 6 does not beat 7 without the skill" in capsys.readouterr().out


def test_sonnet_fails_when_it_spends_no_less_than_plain_opus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    write_run(iteration / "sonnet" / "first-case", 5, 7, 7)
    assert run_main(iteration, write_reference(tmp_path), "sonnet") == 1
    assert "spend $9.00 is not below plain opus's $9.00" in capsys.readouterr().out


def test_sonnet_fails_when_its_total_score_is_below_plain_opus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = reference_document()
    document["models"]["sonnet"]["cases"]["first-case"]["with_skill"]["passed"] = 3
    iteration = write_iteration(tmp_path)
    write_run(iteration / "sonnet" / "first-case", 3, 7, 6)
    assert run_main(iteration, write_reference(tmp_path, document), "sonnet") == 1
    assert "total score 6 is below plain opus's 7" in capsys.readouterr().out


@pytest.mark.parametrize(
    "missing",
    [
        "opus/second-case",
        "opus/second-case/with_skill",
        "opus/second-case/with_skill/grading.json",
        "opus/second-case/with_skill/transcripts",
    ],
)
def test_exits_2_naming_a_missing_case_or_arm(
    tmp_path: Path, missing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    target = iteration / missing
    if target.is_file():
        target.unlink()
    else:
        shutil.rmtree(target)
    assert run_main(iteration, write_reference(tmp_path)) == 2
    assert "second-case" in capsys.readouterr().err


def test_exits_2_when_the_expectation_count_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    write_run(iteration / "opus" / "first-case", 6, 8, 10)
    assert run_main(iteration, write_reference(tmp_path)) == 2
    assert "8 expectations, reference has 7" in capsys.readouterr().err


def test_exits_2_on_a_model_the_reference_lacks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = reference_document()
    del document["models"]["sonnet"]
    assert (
        run_main(
            write_iteration(tmp_path), write_reference(tmp_path, document), "sonnet"
        )
        == 2
    )
    assert "sonnet" in capsys.readouterr().err


def _break_figure(document: Document) -> None:
    document["models"]["opus"]["cases"]["first-case"]["without_skill"]["spend_usd"] = (
        None
    )


def _break_budget_case(document: Document) -> None:
    document["models"]["opus"]["max_extra_spend"] = {"usd": 9, "cases": ["third-case"]}


def _break_rival(document: Document) -> None:
    document["models"]["sonnet"]["rival"] = "haiku"


def _break_rival_cases(document: Document) -> None:
    opus = document["models"]["opus"]
    del opus["cases"]["second-case"]
    opus["max_extra_spend"]["cases"] = ["first-case"]


@pytest.mark.parametrize(
    "breakage", [_break_figure, _break_budget_case, _break_rival, _break_rival_cases]
)
def test_exits_2_on_a_malformed_reference(tmp_path: Path, breakage: object) -> None:
    document = reference_document()
    assert callable(breakage)
    breakage(document)
    reference = write_reference(tmp_path, document)
    assert run_main(write_iteration(tmp_path), reference, "sonnet") == 2


def test_shipped_reference_has_one_entry_per_eval_case_for_each_model() -> None:
    evals_dir = Path(__file__).resolve().parent.parent / "evals"
    reference = json.loads((evals_dir / "reference.json").read_text(encoding="utf-8"))
    evals = json.loads((evals_dir / "evals.json").read_text(encoding="utf-8"))
    for section in reference["models"].values():
        assert len(section["cases"]) == len(evals["evals"])


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("models", "opus"), "not an object"),
        (("models", "opus", "cases", "first-case", "total"), 7.5),
        (("models", "opus", "max_extra_spend", "cases"), "first-case"),
        (("models", "opus", "cases"), {}),
        (("models", "sonnet", "rival"), 5),
    ],
)
def test_exits_2_on_a_malformed_reference_field(
    tmp_path: Path, path: tuple[str, ...], value: object
) -> None:
    document = reference_document()
    record = document
    for key in path[:-1]:
        record = record[key]
    record[path[-1]] = value
    reference = write_reference(tmp_path, document)
    assert run_main(write_iteration(tmp_path), reference) == 2
