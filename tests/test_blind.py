import json
from pathlib import Path

import pytest
from blind import main

RUNS = (
    "opus/data-gap/with_skill",
    "opus/data-gap/without_skill",
    "sonnet/data-gap/with_skill",
    "sonnet/data-gap/with_skill-2",
    "sonnet/tone-shift/without_skill",
)


def write_iteration(tmp_path: Path) -> Path:
    iteration = tmp_path / "iteration-5"
    for run in RUNS:
        outputs = iteration / run / "outputs"
        outputs.mkdir(parents=True)
        (outputs / "deliverable.md").write_text(f"text of {run}", encoding="utf-8")
        (outputs / "notes.md").write_text("notes", encoding="utf-8")
        (outputs / "subagents.json").write_text("[]", encoding="utf-8")
    (iteration / "opus" / "data-gap" / "eval_metadata.json").write_text(
        "{}", encoding="utf-8"
    )
    return iteration


def hide(iteration: Path, key: Path) -> int:
    return main(["hide", str(iteration), "--key", str(key)])


def reveal(iteration: Path, key: Path) -> int:
    return main(["reveal", str(iteration), "--key", str(key)])


def blind_runs(iteration: Path) -> list[Path]:
    return sorted(path for path in (iteration / "blind").glob("*/*") if path.is_dir())


def test_copies_each_run_under_an_id_naming_neither_arm_nor_model(
    tmp_path: Path,
) -> None:
    iteration = write_iteration(tmp_path)
    assert hide(iteration, tmp_path / "key.json") == 0
    copies = blind_runs(iteration)
    assert len(copies) == len(RUNS)
    assert {copy.parent.name for copy in copies} == {"data-gap", "tone-shift"}
    for copy in copies:
        for word in ("skill", "with", "opus", "sonnet"):
            assert word not in copy.name
        assert sorted(path.name for path in copy.iterdir()) == [
            "deliverable.md",
            "notes.md",
        ]


def test_maps_each_grade_back_to_the_run_it_came_from(tmp_path: Path) -> None:
    iteration = write_iteration(tmp_path)
    key = tmp_path / "key.json"
    assert hide(iteration, key) == 0
    for copy in blind_runs(iteration):
        text = (copy / "deliverable.md").read_text(encoding="utf-8")
        grading = {"expectations": [{"text": text, "passed": True, "evidence": "e"}]}
        (copy / "grading.json").write_text(json.dumps(grading), encoding="utf-8")
    assert reveal(iteration, key) == 0
    for run in RUNS:
        grading = json.loads((iteration / run / "grading.json").read_text("utf-8"))
        assert grading["expectations"][0]["text"] == f"text of {run}"


def test_refuses_a_key_inside_the_iteration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    assert hide(iteration, iteration / "key.json") == 2
    assert "outside" in capsys.readouterr().err
    assert not (iteration / "blind").exists()


@pytest.mark.parametrize("existing", ["blind", "key"])
def test_refuses_to_hide_over_an_earlier_round(tmp_path: Path, existing: str) -> None:
    iteration = write_iteration(tmp_path)
    key = tmp_path / "key.json"
    if existing == "blind":
        (iteration / "blind").mkdir()
    else:
        key.write_text("{}", encoding="utf-8")
    assert hide(iteration, key) == 2


def test_refuses_an_iteration_with_no_runs(tmp_path: Path) -> None:
    (tmp_path / "iteration-5" / "opus" / "data-gap").mkdir(parents=True)
    assert hide(tmp_path / "iteration-5", tmp_path / "key.json") == 2


def test_reveal_exits_2_naming_an_ungraded_copy_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = write_iteration(tmp_path)
    key = tmp_path / "key.json"
    assert hide(iteration, key) == 0
    copies = blind_runs(iteration)
    for copy in copies[1:]:
        (copy / "grading.json").write_text('{"expectations": []}', encoding="utf-8")
    assert reveal(iteration, key) == 2
    assert copies[0].name in capsys.readouterr().err
    assert not any((iteration / run / "grading.json").exists() for run in RUNS)


@pytest.mark.parametrize(
    "key_text",
    [
        "[]",
        '{"abc": 5}',
        '{"abc": "../outside/run"}',
        '{"abc": "opus/data-gap"}',
    ],
)
def test_reveal_exits_2_on_a_malformed_key(tmp_path: Path, key_text: str) -> None:
    iteration = write_iteration(tmp_path)
    key = tmp_path / "key.json"
    key.write_text(key_text, encoding="utf-8")
    assert reveal(iteration, key) == 2


def test_reveal_exits_2_on_a_grade_that_lists_no_expectations(
    tmp_path: Path,
) -> None:
    iteration = write_iteration(tmp_path)
    key = tmp_path / "key.json"
    assert hide(iteration, key) == 0
    for copy in blind_runs(iteration):
        (copy / "grading.json").write_text('{"passed": 3}', encoding="utf-8")
    assert reveal(iteration, key) == 2
