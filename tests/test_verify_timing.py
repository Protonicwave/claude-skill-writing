import subprocess
import time
from collections.abc import Sequence

import pytest
import verify_timing
from verify_timing import main


class FakeVerify:
    """Stands in for the verify.py process and the clock: each run lasts as given."""

    def __init__(self, seconds: Sequence[float], exit_code: int = 0) -> None:
        self.seconds = list(seconds)
        self.exit_code = exit_code
        self.commands: list[list[str]] = []
        self.now = 0.0

    def run(
        self, command: list[str], **options: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert options["timeout"] == verify_timing.RUN_TIMEOUT_SECONDS
        self.commands.append(command)
        self.now += self.seconds.pop(0)
        return subprocess.CompletedProcess(command, self.exit_code, b"", b"HTTP 503")

    def perf_counter(self) -> float:
        return self.now


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeVerify:
    process = FakeVerify([])
    monkeypatch.setattr(subprocess, "run", process.run)
    monkeypatch.setattr(time, "perf_counter", process.perf_counter)
    return process


def test_prints_each_run_and_the_median_within_the_budget(
    fake: FakeVerify, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.seconds = [5.0, 3.0, 4.0]
    assert main(["--max-seconds", "4"]) == 0
    out = capsys.readouterr().out
    assert "run 1: 5.0 s" in out
    assert "median 4.0 s, budget 4.0 s: within" in out
    assert all(command[-1] == "-" for command in fake.commands)


def test_exits_1_when_the_median_is_over_the_budget(
    fake: FakeVerify, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.seconds = [5.0]
    assert main(["--runs", "1", "--max-seconds", "4.9"]) == 1
    assert "budget 4.9 s: over" in capsys.readouterr().out


def test_default_budget_is_the_ratio_of_the_sequential_figure(
    fake: FakeVerify, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.seconds = [1.0, 1.0, 1.0]
    main([])
    budget = verify_timing.BUDGET_RATIO * verify_timing.SEQUENTIAL_SECONDS
    assert f"budget {budget:.1f} s" in capsys.readouterr().out


def test_exits_2_when_a_run_does_not_verify_every_source(
    fake: FakeVerify, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.seconds = [1.0]
    fake.exit_code = 1
    assert main(["--runs", "1"]) == 2
    assert "exited 1, not 0: HTTP 503" in capsys.readouterr().err


def test_exits_2_when_a_run_passes_its_time_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def hang(command: list[str], **_options: object) -> None:
        raise subprocess.TimeoutExpired(command, 600)

    monkeypatch.setattr(subprocess, "run", hang)
    assert main(["--runs", "1"]) == 2
    assert "run 1: run passed 600 s" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--runs", "0"],
        ["--runs", "two"],
        ["--max-seconds", "0"],
        ["--max-seconds", "x"],
        ["--max-seconds", "inf"],
    ],
)
def test_rejects_a_bad_run_count_or_budget(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(argv)
    assert stopped.value.code == 2
