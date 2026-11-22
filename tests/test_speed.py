import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from speed import main

# A dollar per input token, so a run's spend is the token count its transcript gives.
PRICES = {
    "date": "2026-11-22",
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
START = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


def stamp(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).isoformat()


def message(name: str, seconds: float | None, tokens: int = 0) -> dict[str, object]:
    entry: dict[str, object] = {
        "type": "assistant",
        "message": {
            "id": name,
            "model": "model-a",
            "usage": {
                "input_tokens": tokens,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 0,
                    "ephemeral_1h_input_tokens": 0,
                },
                "speed": "standard",
            },
        },
    }
    if seconds is not None:
        entry["timestamp"] = stamp(seconds)
    return entry


def write_transcript(run: Path, agent_id: str, entries: list[object]) -> None:
    directory = run / "transcripts"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"agent-{agent_id}.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )


def make_run(run: Path, *, seconds: float, spend: int, passed: int) -> Path:
    """A run whose transcript spans `seconds` and costs `spend` dollars."""
    run.mkdir(parents=True)
    (run / "grading.json").write_text(
        json.dumps({"summary": {"passed": passed, "total": 7}}), encoding="utf-8"
    )
    write_transcript(run, "a1", [message("m1", 0, spend), message("m2", seconds, 0)])
    return run


@pytest.fixture
def reference(tmp_path: Path) -> Path:
    path = tmp_path / "reference.json"
    path.write_text(json.dumps({"prices": PRICES}), encoding="utf-8")
    return path


def speed(iteration: Path, reference: Path, *extra: str, arm: str = "new") -> int:
    return main(
        [
            str(iteration),
            "--model",
            "opus",
            "--arm",
            arm,
            "--against",
            "old",
            "--reference",
            str(reference),
            *extra,
        ]
    )


def two_cases(iteration: Path) -> None:
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    make_run(iteration / "opus" / "first" / "new", seconds=60, spend=8, passed=5)
    make_run(iteration / "opus" / "second" / "old", seconds=300, spend=20, passed=6)
    make_run(iteration / "opus" / "second" / "new", seconds=200, spend=20, passed=7)


def test_prints_median_score_spend_and_seconds_for_each_case_and_arm(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    two_cases(iteration)
    make_run(iteration / "opus" / "first" / "new-2", seconds=80, spend=12, passed=7)
    make_run(iteration / "opus" / "first" / "new-3", seconds=70, spend=9, passed=3)

    assert speed(iteration, reference, "--max-seconds-ratio", "0.9") == 0

    lines = capsys.readouterr().out.splitlines()
    first = next(line for line in lines if line.startswith("first"))
    assert first.split() == ["first", "5", "5", "$10.00", "$9.00", "100s", "70s"]
    second = next(line for line in lines if line.startswith("second"))
    assert second.split() == ["second", "6", "7", "$20.00", "$20.00", "300s", "200s"]
    total = next(line for line in lines if line.startswith("total"))
    assert total.split() == ["total", "11", "12", "$30.00", "$29.00", "400s", "270s"]
    assert "seconds ratio 0.68 against budget 0.90" in "\n".join(lines)


def test_compares_with_an_arm_of_another_iteration(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    earlier = tmp_path / "earlier"
    make_run(earlier / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    later = tmp_path / "later"
    make_run(later / "opus" / "first" / "new", seconds=50, spend=9, passed=5)

    code = speed(later, reference, "--baseline-iteration", str(earlier))

    assert code == 0
    assert "50s" in capsys.readouterr().out


def test_fails_when_seconds_exceed_the_ratio(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    two_cases(iteration)

    assert speed(iteration, reference, "--max-seconds-ratio", "0.5") == 1

    assert "FAIL: seconds 260s are 0.65 of 400s, over the 0.50 budget" in (
        capsys.readouterr().out
    )


def test_fails_when_spend_rises(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    make_run(iteration / "opus" / "first" / "new", seconds=50, spend=11, passed=5)

    assert speed(iteration, reference) == 1

    assert "FAIL: spend $11.00 is above $10.00" in capsys.readouterr().out


def test_fails_naming_a_case_whose_score_falls(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    make_run(iteration / "opus" / "first" / "new", seconds=50, spend=10, passed=4)
    make_run(iteration / "opus" / "second" / "old", seconds=100, spend=10, passed=2)
    make_run(iteration / "opus" / "second" / "new", seconds=50, spend=10, passed=6)

    assert speed(iteration, reference) == 1

    out = capsys.readouterr().out
    assert "FAIL: first scored 4, baseline 5" in out
    assert "second scored" not in out


def test_spans_the_run_and_the_subagents_it_spawned(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    spawn = {"toolUseResult": {"agentId": "b2"}, "timestamp": stamp(5)}
    write_transcript(run, "a1", [message("m1", 0, 10), spawn, message("m2", 10)])
    write_transcript(run, "b2", [message("m3", 5), message("m4", 30)])

    speed(iteration, reference)

    assert "30s" in capsys.readouterr().out


def test_ignores_entries_without_a_timestamp(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    write_transcript(
        run, "a1", [message("m1", 0, 10), message("m2", None), message("m3", 40)]
    )

    speed(iteration, reference)

    assert "40s" in capsys.readouterr().out


def test_exits_2_naming_a_run_with_no_timestamps(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    write_transcript(run, "a1", [message("m1", None, 10)])

    assert speed(iteration, reference) == 2

    err = capsys.readouterr().err
    assert str(run) in err
    assert "no timestamps" in err


def test_exits_2_naming_a_run_with_no_transcript(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    (run / "transcripts" / "agent-a1.jsonl").unlink()

    assert speed(iteration, reference) == 2

    assert str(run) in capsys.readouterr().err


@pytest.mark.parametrize("line", ["not json", "[1]", json.dumps({"timestamp": 5})])
def test_exits_2_on_a_malformed_transcript_line(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    (run / "transcripts" / "agent-a1.jsonl").write_text(line + "\n", encoding="utf-8")

    assert speed(iteration, reference) == 2

    assert str(run) in capsys.readouterr().err


def test_exits_2_naming_a_timestamp_that_is_not_a_date(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    entry = {**message("m1", 0, 10), "timestamp": "yesterday"}
    write_transcript(run, "a1", [entry])

    assert speed(iteration, reference) == 2

    assert "yesterday" in capsys.readouterr().err


def test_exits_2_naming_a_timestamp_with_no_zone(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    entry = {**message("m1", 0, 10), "timestamp": "2026-11-22T09:00:00"}
    write_transcript(run, "a1", [entry])

    assert speed(iteration, reference) == 2

    assert "2026-11-22T09:00:00" in capsys.readouterr().err


def test_exits_2_naming_a_case_present_in_one_arm_only(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    two_cases(iteration)
    make_run(iteration / "opus" / "third" / "old", seconds=100, spend=10, passed=5)

    assert speed(iteration, reference) == 2

    err = capsys.readouterr().err
    assert "third" in err
    assert "new" in err


def test_exits_2_when_the_arm_has_no_runs_at_all(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)

    assert speed(iteration, reference) == 2

    assert "new" in capsys.readouterr().err


def test_ignores_arms_whose_name_only_starts_with_the_arm(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    two_cases(iteration)
    make_run(iteration / "opus" / "first" / "new_other", seconds=1, spend=1, passed=0)

    assert speed(iteration, reference, "--max-seconds-ratio", "0.9") == 0

    assert "60s" in capsys.readouterr().out


def test_exits_2_on_a_missing_grading_file(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    (run / "grading.json").unlink()

    assert speed(iteration, reference) == 2

    assert "grading.json" in capsys.readouterr().err


@pytest.mark.parametrize(
    "grading", [[], {"summary": []}, {"summary": {"passed": "5"}}, {"summary": {}}]
)
def test_exits_2_on_a_grading_file_without_a_passed_count(
    tmp_path: Path,
    reference: Path,
    capsys: pytest.CaptureFixture[str],
    grading: object,
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    (run / "grading.json").write_text(json.dumps(grading), encoding="utf-8")

    assert speed(iteration, reference) == 2

    assert str(run) in capsys.readouterr().err


def test_exits_2_on_a_model_with_no_price(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    entry = message("m1", 0, 10)
    entry["message"]["model"] = "model-z"  # type: ignore[index]
    write_transcript(run, "a1", [entry, message("m2", 5)])

    assert speed(iteration, reference) == 2

    assert "model-z" in capsys.readouterr().err


def test_exits_2_naming_a_run_whose_timestamps_span_no_time(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    make_run(iteration / "opus" / "first" / "old", seconds=100, spend=10, passed=5)
    run = make_run(iteration / "opus" / "first" / "new", seconds=10, spend=10, passed=5)
    write_transcript(run, "a1", [message("m1", 3, 10)])

    assert speed(iteration, reference) == 2

    assert "span no time" in capsys.readouterr().err


@pytest.mark.parametrize("ratio", ["0", "-1", "fast", "nan", "inf"])
def test_rejects_a_ratio_that_is_not_a_positive_number(
    tmp_path: Path, reference: Path, ratio: str
) -> None:
    iteration = tmp_path / "iteration"
    two_cases(iteration)

    with pytest.raises(SystemExit) as stop:
        speed(iteration, reference, "--max-seconds-ratio", ratio)

    assert stop.value.code == 2


def test_exits_2_on_a_transcript_over_the_size_limit(
    tmp_path: Path,
    reference: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iteration = tmp_path / "iteration"
    two_cases(iteration)
    monkeypatch.setattr("speed.MAX_TRANSCRIPT_BYTES", 10)

    assert speed(iteration, reference) == 2

    assert "over 10 bytes" in capsys.readouterr().err


def test_exits_2_when_the_model_has_no_runs_of_either_arm(
    tmp_path: Path, reference: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    iteration = tmp_path / "iteration"
    (iteration / "opus" / "first").mkdir(parents=True)

    assert speed(iteration, reference) == 2

    assert "no case has a new or old run" in capsys.readouterr().err
