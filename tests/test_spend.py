import json
from pathlib import Path

import pytest
import spend
from spend import capture, load_prices, main, run_spend

# A dollar per token for each kind of token, so a run's spend reads off its counts.
RATES = {
    "input": 1_000_000,
    "output": 2_000_000,
    "cache_write_5m": 3_000_000,
    "cache_write_1h": 4_000_000,
    "cache_read": 5_000_000,
}
LONG_RATES = {name: rate * 10 for name, rate in RATES.items()}
PRICES = {
    "date": "2026-11-19",
    "usd_per_million_tokens": {
        "model-a": RATES,
        "model-b": {**RATES, "input": 7_000_000},
        "model-long": {**RATES, "long_prompt": {"over_tokens": 10, **LONG_RATES}},
    },
}


def write_reference(tmp_path: Path) -> Path:
    path = tmp_path / "reference.json"
    path.write_text(json.dumps({"prices": PRICES}), encoding="utf-8")
    return path


def assistant(message_id: str, model: str, **counts: int) -> dict[str, object]:
    usage = {
        "input_tokens": counts.get("input", 0),
        "output_tokens": counts.get("output", 0),
        "cache_creation_input_tokens": counts.get("write_5m", 0)
        + counts.get("write_1h", 0),
        "cache_read_input_tokens": counts.get("read", 0),
        "cache_creation": {
            "ephemeral_5m_input_tokens": counts.get("write_5m", 0),
            "ephemeral_1h_input_tokens": counts.get("write_1h", 0),
        },
        "speed": "standard",
    }
    message = {"id": message_id, "model": model, "usage": usage}
    return {"type": "assistant", "message": message}


def spawned(agent_id: str) -> dict[str, object]:
    return {"type": "user", "toolUseResult": {"agentId": agent_id}}


def write_transcript(directory: Path, agent_id: str, entries: list[object]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"agent-{agent_id}.jsonl"
    path.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )
    return path


def spend_of(tmp_path: Path, entries: list[object]) -> float:
    run = tmp_path / "run"
    write_transcript(run / "transcripts", "a1", entries)
    return run_spend(run, load_prices(write_reference(tmp_path)))


def test_prices_each_kind_of_token_at_its_model_rate(tmp_path: Path) -> None:
    entries: list[object] = [
        assistant("m1", "model-a", input=1, output=1, write_5m=1, write_1h=1, read=1),
        assistant("m2", "model-b", input=1),
    ]
    assert spend_of(tmp_path, entries) == 1 + 2 + 3 + 4 + 5 + 7


def test_counts_a_message_streamed_over_several_entries_once(tmp_path: Path) -> None:
    entries: list[object] = [assistant("m1", "model-a", output=3)] * 3
    assert spend_of(tmp_path, entries) == 6


def test_prices_a_prompt_over_the_threshold_on_the_long_card(tmp_path: Path) -> None:
    entries: list[object] = [
        assistant("short", "model-long", input=4, read=6),
        assistant("long", "model-long", input=5, read=6),
    ]
    assert spend_of(tmp_path, entries) == (4 + 6 * 5) + (5 + 6 * 5) * 10


def test_skips_entries_that_are_not_priced_messages(tmp_path: Path) -> None:
    entries: list[object] = [
        {"type": "user", "message": {"content": "hello"}},
        {"type": "user", "toolUseResult": "plain text result"},
        assistant("m1", "model-a", input=2),
    ]
    assert spend_of(tmp_path, entries) == 2


def test_adds_the_spend_of_subagents_the_run_spawned(tmp_path: Path) -> None:
    run = tmp_path / "run"
    transcripts = run / "transcripts"
    write_transcript(
        transcripts, "a1", [spawned("a2"), assistant("m1", "model-a", input=1)]
    )
    write_transcript(
        transcripts, "a2", [spawned("a3"), assistant("m2", "model-b", input=1)]
    )
    write_transcript(transcripts, "a3", [assistant("m3", "model-a", output=1)])
    assert run_spend(run, load_prices(write_reference(tmp_path))) == 1 + 7 + 2


def test_rejects_a_run_whose_subagent_transcript_is_missing(tmp_path: Path) -> None:
    run = tmp_path / "run"
    write_transcript(run / "transcripts", "a1", [spawned("a9")])
    with pytest.raises(ValueError, match="a9"):
        run_spend(run, load_prices(write_reference(tmp_path)))


@pytest.mark.parametrize("transcripts", [None, "empty"])
def test_rejects_a_run_with_no_transcripts(
    tmp_path: Path, transcripts: str | None
) -> None:
    run = tmp_path / "run"
    if transcripts:
        (run / "transcripts").mkdir(parents=True)
    with pytest.raises(ValueError, match="transcripts"):
        run_spend(run, load_prices(write_reference(tmp_path)))


def test_rejects_a_model_with_no_price(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model-z"):
        spend_of(tmp_path, [assistant("m1", "model-z", input=1)])


def test_rejects_a_speed_the_table_does_not_price(tmp_path: Path) -> None:
    entry = assistant("m1", "model-a", input=1)
    message = entry["message"]
    assert isinstance(message, dict)
    message["usage"]["speed"] = "fast"
    with pytest.raises(ValueError, match="fast"):
        spend_of(tmp_path, [entry])


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        json.dumps([1]),
        json.dumps({"type": "assistant", "message": {"id": "m1"}}),
        json.dumps({"type": "assistant", "message": "text"}),
        json.dumps(spawned("../escape")),
    ],
)
def test_rejects_a_malformed_transcript_line(tmp_path: Path, line: str) -> None:
    run = tmp_path / "run"
    (run / "transcripts").mkdir(parents=True)
    (run / "transcripts" / "agent-a1.jsonl").write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"agent-a1\.jsonl:1"):
        run_spend(run, load_prices(write_reference(tmp_path)))


def test_rejects_usage_whose_cache_writes_do_not_add_up(tmp_path: Path) -> None:
    entry = assistant("m1", "model-a", write_5m=2)
    message = entry["message"]
    assert isinstance(message, dict)
    message["usage"]["cache_creation_input_tokens"] = 3
    with pytest.raises(ValueError, match="cache"):
        spend_of(tmp_path, [entry])


@pytest.mark.parametrize(
    "prices",
    [
        {"date": "2026-11-19"},
        {"date": "2026-11-19", "usd_per_million_tokens": {"model-a": {"input": 1}}},
        {"date": "2026-11-19", "usd_per_million_tokens": {"m": {**RATES, "input": -1}}},
        {"usd_per_million_tokens": {"model-a": RATES}},
    ],
)
def test_rejects_a_malformed_price_table(tmp_path: Path, prices: object) -> None:
    path = tmp_path / "reference.json"
    path.write_text(json.dumps({"prices": prices}), encoding="utf-8")
    with pytest.raises(ValueError, match="price"):
        load_prices(path)


def test_shipped_prices_cover_every_model_the_evals_run() -> None:
    reference = Path(__file__).resolve().parent.parent / "evals" / "reference.json"
    prices = load_prices(reference)
    assert {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"} <= set(prices)


def test_prints_the_spend_of_each_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = write_reference(tmp_path)
    run = tmp_path / "run"
    write_transcript(run / "transcripts", "a1", [assistant("m1", "model-a", input=2)])
    assert main(["price", str(run), "--reference", str(reference)]) == 0
    assert "$2.0000" in capsys.readouterr().out


def test_exits_2_naming_a_run_it_cannot_price(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = write_reference(tmp_path)
    assert main(["price", str(tmp_path / "gone"), "--reference", str(reference)]) == 2
    assert "gone" in capsys.readouterr().err


def test_captures_a_run_and_every_subagent_it_spawned(tmp_path: Path) -> None:
    source = tmp_path / "session" / "subagents"
    write_transcript(source, "a1", [spawned("a2"), assistant("m1", "model-a", input=1)])
    write_transcript(source, "a2", [spawned("a3"), spawned("a2")])
    write_transcript(source, "a3", [assistant("m3", "model-a", output=1)])
    write_transcript(source, "other", [assistant("m4", "model-a", input=100)])
    run = tmp_path / "run"
    assert main(["capture", "a1", str(run), "--from", str(source)]) == 0
    copied = sorted(path.name for path in (run / "transcripts").iterdir())
    assert copied == ["agent-a1.jsonl", "agent-a2.jsonl", "agent-a3.jsonl"]
    assert run_spend(run, load_prices(write_reference(tmp_path))) == 3


def test_capture_exits_2_naming_a_missing_subagent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "subagents"
    write_transcript(source, "a1", [spawned("a2")])
    assert main(["capture", "a1", str(tmp_path / "run"), "--from", str(source)]) == 2
    assert "agent-a2.jsonl" in capsys.readouterr().err


def test_capture_refuses_a_run_that_already_holds_transcripts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "subagents"
    write_transcript(source, "a1", [])
    run = tmp_path / "run"
    write_transcript(run / "transcripts", "old", [])
    assert main(["capture", "a1", str(run), "--from", str(source)]) == 2
    assert "already" in capsys.readouterr().err


def test_capture_rejects_an_agent_id_that_is_not_one(tmp_path: Path) -> None:
    source = tmp_path / "subagents"
    source.mkdir()
    assert main(["capture", "../a1", str(tmp_path / "run"), "--from", str(source)]) == 2


@pytest.mark.parametrize("message_id", [None, 7])
def test_rejects_an_assistant_message_without_a_string_id(
    tmp_path: Path, message_id: object
) -> None:
    entry = assistant("m1", "model-a")
    message = entry["message"]
    assert isinstance(message, dict)
    message["id"] = message_id
    with pytest.raises(ValueError, match="message id"):
        spend_of(tmp_path, [entry])


def test_rejects_a_negative_token_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="input_tokens"):
        spend_of(tmp_path, [assistant("m1", "model-a", input=-1)])


def test_rejects_a_transcript_over_the_size_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spend, "MAX_TRANSCRIPT_BYTES", 10)
    with pytest.raises(ValueError, match="bytes"):
        spend_of(tmp_path, [assistant("m1", "model-a", input=1)])


def test_capture_stops_at_the_agent_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spend, "MAX_TRANSCRIPTS_PER_RUN", 1)
    source = tmp_path / "subagents"
    write_transcript(source, "a1", [spawned("a2")])
    write_transcript(source, "a2", [])
    with pytest.raises(ValueError, match="over 1 agents"):
        capture(source, "a1", tmp_path / "run")
