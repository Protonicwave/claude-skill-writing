"""List-price spend of an eval run, read from its own and its subagents' transcripts.

Usage:
  python evals/spend.py capture AGENT_ID RUN_DIR --from SUBAGENTS_DIR
  python evals/spend.py price RUN_DIR... [--reference PATH]

`capture` copies the transcript of the run's agent, and of every subagent it
spawned at any depth, from Claude Code's session folder into
RUN_DIR/transcripts/. `price` prints each run's spend in US dollars at the
list prices in the reference file. Each assistant message is priced once,
however many transcript entries it was streamed over, at its own model's
rates. Exit 0 on success, 2 when a transcript, a subagent's transcript or a
model's price is missing, or an input is malformed.

Not counted: requests a tool makes outside the transcript, such as a web
search's own model call.
"""

import argparse
import json
import re
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REFERENCE = Path(__file__).resolve().parent / "reference.json"
TRANSCRIPTS = "transcripts"
TOKENS_PER_MILLION = 1_000_000
MAX_TRANSCRIPT_BYTES = 200_000_000
MAX_TRANSCRIPTS_PER_RUN = 200
PRICED_SPEED = "standard"
# Claude Code's agent ids are short hex strings; anything else could escape the folder.
AGENT_ID = re.compile(r"[A-Za-z0-9]{1,64}")
RATE_NAMES = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")


@dataclass(frozen=True, slots=True)
class Rates:
    """US dollars per million tokens of each kind."""

    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float


@dataclass(frozen=True, slots=True)
class ModelPrice:
    rates: Rates
    # A longer prompt is billed on a second rate card: (threshold in tokens, rates).
    long_prompt: tuple[int, Rates] | None


@dataclass(frozen=True, slots=True)
class Usage:
    model: str
    input: int
    output: int
    cache_write_5m: int
    cache_write_1h: int
    cache_read: int

    @property
    def prompt_tokens(self) -> int:
        return self.input + self.cache_write_5m + self.cache_write_1h + self.cache_read


@dataclass(frozen=True, slots=True)
class Transcript:
    usages: dict[str, Usage]
    spawned: list[str]


Prices = dict[str, ModelPrice]


def _object(value: object, where: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"expected {where} to be a JSON object, got {value!r}")
    return value


def _count(record: dict[str, object], name: str, where: object) -> int:
    value = record.get(name)
    # JSON true and false load as bool, which Python treats as an int.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"expected {name} in {where} to be a count, got {value!r}")
    return value


def _rate(record: dict[str, object], name: str, where: str) -> float:
    value = record.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError(f"expected price {name} for {where} to be >= 0, got {value!r}")
    return float(value)


def _rates(record: dict[str, object], where: str) -> Rates:
    return Rates(*(_rate(record, name, where) for name in RATE_NAMES))


def _model_price(model: str, value: object) -> ModelPrice:
    record = _object(value, f"the price of {model}")
    long_prompt = None
    if "long_prompt" in record:
        long_record = _object(
            record["long_prompt"], f"the long-prompt price of {model}"
        )
        threshold = _count(long_record, "over_tokens", f"the price of {model}")
        long_prompt = (threshold, _rates(long_record, f"{model} long prompts"))
    return ModelPrice(_rates(record, model), long_prompt)


def load_prices(reference: Path) -> Prices:
    """Read the dated price table from the reference; raise ValueError if malformed."""
    document = _object(json.loads(reference.read_text(encoding="utf-8")), reference)
    table = _object(document.get("prices"), f"the prices in {reference}")
    if not isinstance(table.get("date"), str):
        raise ValueError(f"expected the prices in {reference} to give their date")
    models = _object(
        table.get("usd_per_million_tokens"), f"the price list in {reference}"
    )
    return {model: _model_price(model, value) for model, value in models.items()}


def _usage(message: dict[str, object], where: str) -> Usage:
    model = message.get("model")
    if not isinstance(model, str):
        raise ValueError(f"expected a model name at {where}, got {model!r}")
    usage = _object(message.get("usage"), f"the usage at {where}")
    speed = usage.get("speed", PRICED_SPEED)
    if speed != PRICED_SPEED:
        raise ValueError(f"no price for {speed!r} speed at {where}")
    written = _count(usage, "cache_creation_input_tokens", where)
    split = _object(usage.get("cache_creation"), f"the cache writes at {where}")
    write_5m = _count(split, "ephemeral_5m_input_tokens", where)
    write_1h = _count(split, "ephemeral_1h_input_tokens", where)
    if write_5m + write_1h != written:
        raise ValueError(
            f"cache writes at {where} split as {write_5m} + {write_1h}, total {written}"
        )
    return Usage(
        model=model,
        input=_count(usage, "input_tokens", where),
        output=_count(usage, "output_tokens", where),
        cache_write_5m=write_5m,
        cache_write_1h=write_1h,
        cache_read=_count(usage, "cache_read_input_tokens", where),
    )


def _spawned_agent(entry: dict[str, object], where: str) -> str | None:
    result = entry.get("toolUseResult")
    if not isinstance(result, dict) or "agentId" not in result:
        return None
    agent_id = result["agentId"]
    if not isinstance(agent_id, str) or not AGENT_ID.fullmatch(agent_id):
        raise ValueError(f"expected an agent id at {where}, got {agent_id!r}")
    return agent_id


def _entries(path: Path) -> Iterator[tuple[str, dict[str, object]]]:
    if path.stat().st_size > MAX_TRANSCRIPT_BYTES:
        raise ValueError(f"{path} is over {MAX_TRANSCRIPT_BYTES} bytes")
    with path.open(encoding="utf-8") as lines:
        for number, line in enumerate(lines, start=1):
            where = f"{path}:{number}"
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as err:
                raise ValueError(f"{where} is not JSON: {err}") from err
            yield where, _object(entry, where)


def read_transcript(path: Path) -> Transcript:
    """Each message's usage by id, from its last streamed entry, and agents spawned."""
    usages: dict[str, Usage] = {}
    spawned: list[str] = []
    for where, entry in _entries(path):
        agent_id = _spawned_agent(entry, where)
        if agent_id is not None:
            spawned.append(agent_id)
        if entry.get("type") != "assistant":
            continue
        message = _object(entry.get("message"), f"the message at {where}")
        message_id = message.get("id")
        if not isinstance(message_id, str):
            raise ValueError(f"expected a message id at {where}, got {message_id!r}")
        usages[message_id] = _usage(message, where)
    return Transcript(usages, spawned)


def price(usage: Usage, prices: Prices) -> float:
    """The list price of one message in US dollars."""
    if usage.model not in prices:
        raise ValueError(f"no price for model {usage.model!r}")
    model = prices[usage.model]
    rates = model.rates
    if model.long_prompt is not None and usage.prompt_tokens > model.long_prompt[0]:
        rates = model.long_prompt[1]
    micro_dollars = (
        usage.input * rates.input
        + usage.output * rates.output
        + usage.cache_write_5m * rates.cache_write_5m
        + usage.cache_write_1h * rates.cache_write_1h
        + usage.cache_read * rates.cache_read
    )
    return micro_dollars / TOKENS_PER_MILLION


def _transcript_path(directory: Path, agent_id: str) -> Path:
    if not AGENT_ID.fullmatch(agent_id):
        raise ValueError(f"expected an agent id, got {agent_id!r}")
    return directory / f"agent-{agent_id}.jsonl"


def run_spend(run_dir: Path, prices: Prices) -> float:
    """List price of a run's captured transcripts; ValueError if one is missing."""
    directory = run_dir / TRANSCRIPTS
    paths = sorted(directory.glob("agent-*.jsonl")) if directory.is_dir() else []
    if not paths:
        raise ValueError(f"{directory} holds no transcripts")
    usages: dict[str, Usage] = {}
    for path in paths:
        transcript = read_transcript(path)
        for agent_id in transcript.spawned:
            if not _transcript_path(directory, agent_id).is_file():
                raise ValueError(
                    f"{path} spawned agent {agent_id}, missing from {directory}"
                )
        usages.update(transcript.usages)
    return sum(price(usage, prices) for usage in usages.values())


def capture(source: Path, agent_id: str, run_dir: Path) -> list[Path]:
    """Copy the agent's and its subagents' transcripts into the run; return them."""
    target = run_dir / TRANSCRIPTS
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"{target} already holds transcripts")
    pending = [agent_id]
    seen = {agent_id}
    copied: list[Path] = []
    while pending:
        if len(copied) == MAX_TRANSCRIPTS_PER_RUN:
            raise ValueError(f"run spawned over {MAX_TRANSCRIPTS_PER_RUN} agents")
        path = _transcript_path(source, pending.pop())
        if not path.is_file():
            raise ValueError(f"{path} is missing")
        children = [
            child for child in read_transcript(path).spawned if child not in seen
        ]
        seen.update(children)
        pending.extend(children)
        target.mkdir(parents=True, exist_ok=True)
        copied.append(Path(shutil.copyfile(path, target / path.name)))
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List-price spend of eval runs.")
    commands = parser.add_subparsers(dest="command", required=True)
    capturing = commands.add_parser("capture", help="copy a run's transcripts")
    capturing.add_argument("agent_id", help="the run's agent id")
    capturing.add_argument("run_dir", type=Path, help="the run directory")
    capturing.add_argument(
        "--from", dest="source", type=Path, required=True, help="the subagents folder"
    )
    pricing = commands.add_parser("price", help="print each run's spend")
    pricing.add_argument("run_dirs", nargs="+", type=Path, help="run directories")
    pricing.add_argument(
        "--reference", type=Path, default=DEFAULT_REFERENCE, help="the price table"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            copied = capture(args.source, args.agent_id, args.run_dir)
            print(f"{args.run_dir}: {len(copied)} transcripts captured")
        else:
            prices = load_prices(args.reference)
            for run_dir in args.run_dirs:
                print(f"{run_dir}  ${run_spend(run_dir, prices):.4f}")
    except (OSError, ValueError) as err:
        print(f"cannot {args.command}: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover: entry point; main is tested directly
