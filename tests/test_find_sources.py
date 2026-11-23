import io
import itertools
import json
import sys
import threading
import urllib.parse
from datetime import date
from pathlib import Path
from typing import Any

import find_sources
import pytest
from find_sources import MAX_CLAIMS, main, search_claims
from gap_search import MAX_RUN_SECONDS
from verify import RegistryUnavailableError

# Any: the tables mix claim text and query lists, as the JSON file does.
CLAIMS: list[dict[str, Any]] = [
    {
        "claim": "Neural samplers propose Ising configurations.",
        "queries": [
            "neural network sampler Ising model",
            "autoregressive network spins",
        ],
    },
    {
        "claim": "Self-learning Monte Carlo fits an effective model.",
        "queries": [
            "self-learning Monte Carlo",
            "effective Hamiltonian cluster updates",
            "machine learning Monte Carlo",
        ],
    },
]


def openalex(*works: dict[str, object]) -> bytes:
    return json.dumps({"meta": {"count": len(works)}, "results": list(works)}).encode()


def work(number: int, title: str = "A neural sampler") -> dict[str, object]:
    return {
        "id": f"https://openalex.org/W{number}",
        "doi": f"https://doi.org/10.1000/w{number}",
        "title": title,
        "publication_year": 2020,
        "abstract_inverted_index": {"We": [0], "sample": [1], "spins.": [2]},
    }


def feed(*arxiv_ids: str) -> bytes:
    entries = "".join(
        f"<entry><id>http://arxiv.org/abs/{arxiv_id}</id>"
        "<published>2019-10-30T10:00:00Z</published>"
        f"<title>Preprint {arxiv_id}</title><summary>We sample spins.</summary>"
        "</entry>"
        for arxiv_id in arxiv_ids
    )
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        f'xmlns:arxiv="http://arxiv.org/schemas/atom">{entries}</feed>'
    ).encode()


def searched(url: str) -> str:
    fields = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    if "search" in fields:
        return fields["search"][0]
    terms = fields["search_query"][0].split(" AND ")
    return " ".join(term.split(":")[1].strip('"') for term in terms)


class FakeRegistry:
    """Answers each request a route names by registry and words; others get no hits.

    A route's answer is a body or an exception to raise. Safe across threads.
    """

    def __init__(
        self, routes: dict[tuple[str, str], bytes | Exception] | None = None
    ) -> None:
        self.routes = routes or {}
        self.requested: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, url: str) -> bytes | None:
        with self.lock:
            self.requested.append(url)
        registry = "arxiv" if "arxiv" in url else "openalex"
        answer = self.routes.get((registry, searched(url)))
        if isinstance(answer, Exception):
            raise answer
        if answer is not None:
            return answer
        return feed() if "arxiv" in url else openalex()


def write_claims(folder: Path, claims: object) -> Path:
    path = folder / "claims.json"
    path.write_text(json.dumps(claims), encoding="utf-8")
    return path


def run_main(
    monkeypatch: pytest.MonkeyPatch,
    registry: FakeRegistry,
    folder: Path,
    claims: object = CLAIMS,
) -> int:
    monkeypatch.setattr(find_sources, "RegistryClient", lambda: registry)
    claims_path = write_claims(folder, claims)
    return main(["--log", str(folder / "source-search.md"), str(claims_path)])


def test_sends_every_query_to_openalex_and_each_first_query_to_arxiv() -> None:
    registry = FakeRegistry()

    search_claims(find_sources.parse_claims(json.dumps(CLAIMS)), registry)

    openalex_words = [searched(u) for u in registry.requested if "openalex" in u]
    arxiv_words = [searched(u) for u in registry.requested if "arxiv" in u]
    every_query = [query for claim in CLAIMS for query in claim["queries"]]
    assert sorted(openalex_words) == sorted(every_query)
    assert arxiv_words == [claim["queries"][0] for claim in CLAIMS]


def test_lists_each_claims_hits_under_it_and_each_work_once() -> None:
    registry = FakeRegistry(
        {
            ("openalex", "neural network sampler Ising model"): openalex(
                work(1), work(2)
            ),
            ("openalex", "autoregressive network spins"): openalex(work(2)),
            ("openalex", "self-learning Monte Carlo"): openalex(work(2), work(3)),
        }
    )

    results = search_claims(find_sources.parse_claims(json.dumps(CLAIMS)), registry)

    first, second = ([hit.openalex for hit in result.hits] for result in results)
    assert first == ["W2", "W1"]
    assert second == ["W2", "W3"]


def test_sends_openalex_queries_four_at_a_time() -> None:
    arrived = threading.Barrier(4, timeout=2)

    def fetch(url: str) -> bytes:
        if "arxiv" in url:
            return feed()
        arrived.wait()
        return openalex()

    claims = [
        {"claim": f"Claim {n}.", "queries": [f"first query {n}", f"second query {n}"]}
        for n in range(2)
    ]
    results = search_claims(find_sources.parse_claims(json.dumps(claims)), fetch)

    assert all(
        outcome.problem is None for result in results for outcome in result.requests
    )


def test_starts_no_request_after_the_run_time_limit() -> None:
    registry = FakeRegistry()
    clock = itertools.chain([0.0], itertools.repeat(MAX_RUN_SECONDS + 1))

    results = search_claims(
        find_sources.parse_claims(json.dumps(CLAIMS)), registry, now=lambda: next(clock)
    )

    assert registry.requested == []
    problems = [o.problem or "" for result in results for o in result.requests]
    assert all("not searched" in problem for problem in problems)


def test_main_prints_hits_under_their_claims_and_writes_the_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = FakeRegistry(
        {
            ("openalex", "neural network sampler Ising model"): openalex(
                work(1, "Ising | sampler")
            ),
            ("arxiv", "self-learning Monte Carlo"): feed("1610.03137v2"),
        }
    )

    code = run_main(monkeypatch, registry, tmp_path)

    printed = capsys.readouterr().out
    assert code == 0
    assert printed.index("Claim 1: Neural samplers") < printed.index("doi:10.1000/w1")
    assert printed.index("Claim 2: Self-learning") < printed.index("arXiv:1610.03137")
    assert "Ising / sampler" in printed
    log = (tmp_path / "source-search.md").read_text(encoding="utf-8")
    assert date.today().isoformat() in log
    assert all(url in log for url in registry.requested)
    assert "## Claim 2: Self-learning Monte Carlo fits an effective model." in log
    assert "arXiv:1610.03137" in log


def test_main_exits_1_naming_a_failed_request_and_prints_the_other_hits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = FakeRegistry(
        {
            (
                "openalex",
                "neural network sampler Ising model",
            ): RegistryUnavailableError("HTTP 503"),
            ("openalex", "autoregressive network spins"): b"<html>not json</html>",
            ("openalex", "self-learning Monte Carlo"): openalex(work(3)),
        }
    )

    code = run_main(monkeypatch, registry, tmp_path)

    printed = capsys.readouterr().out
    assert code == 1
    assert 'claim 1, OpenAlex q1 "neural network sampler Ising model"' in printed
    assert "unavailable (HTTP 503)" in printed
    assert "malformed answer" in printed
    assert "doi:10.1000/w3" in printed


def test_main_prints_each_claim_its_share_and_logs_every_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(find_sources, "MAX_PRINTED_CHARACTERS", 1200)
    many = openalex(*(work(n, title=f"Work {n} " + "x" * 80) for n in range(5)))
    registry = FakeRegistry(
        {("openalex", q): many for claim in CLAIMS for q in claim["queries"]}
    )

    run_main(monkeypatch, registry, tmp_path)

    printed = capsys.readouterr().out
    assert printed.count("more hits for this claim are in the log.") == 2
    assert "Claim 2:" in printed
    log = (tmp_path / "source-search.md").read_text(encoding="utf-8")
    assert all(f"Work {n} " in log for n in range(5))


def test_main_rerun_answers_from_the_cache_beside_the_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry = FakeRegistry()
    run_main(monkeypatch, registry, tmp_path)
    sent = len(registry.requested)

    run_main(monkeypatch, registry, tmp_path)

    assert len(registry.requested) == sent
    assert (tmp_path / "sources.cache.json").is_file()


def test_main_writes_utf8_whatever_the_console_code_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    written = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(written, encoding="cp1252"))
    registry = FakeRegistry(
        {
            ("openalex", "neural network sampler Ising model"): openalex(
                work(1, "Schrödinger")
            )
        }
    )

    assert run_main(monkeypatch, registry, tmp_path) == 0

    sys.stdout.flush()
    assert "Schrödinger" in written.getvalue().decode("utf-8")


def test_main_prints_to_a_stream_it_cannot_reconfigure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)

    assert run_main(monkeypatch, FakeRegistry(), tmp_path) == 0

    assert "Claim 1:" in stream.getvalue()


def claims_with(**changes: object) -> list[dict[str, object]]:
    return [{**CLAIMS[0], **changes}]


@pytest.mark.parametrize(
    ("claims", "message"),
    [
        ([], "1 to 20 claims"),
        ({"claim": "x"}, "1 to 20 claims"),
        (
            [{"claim": f"Claim {n}.", "queries": ["a b", "c d"]} for n in range(21)],
            "1 to 20 claims",
        ),
        (["a claim"], "claim 1: expected an object"),
        (claims_with(claim=""), "claim 1: expected the claim as text"),
        (claims_with(claim=7), "claim 1: expected the claim as text"),
        (claims_with(queries=[]), "claim 1: expected 2 to 4 queries"),
        (claims_with(queries=["one two"]), "claim 1: expected 2 to 4 queries"),
        (claims_with(queries=["a b", "c d", "e f", "g h", "i j"]), "2 to 4 queries"),
        (claims_with(queries="a b"), "claim 1: expected 2 to 4 queries"),
        (claims_with(queries=["a b", 5]), "claim 1: expected 2 to 4 queries"),
        (claims_with(queries=["one", "two words"]), "claim 1: expected 2 to 8 words"),
        (claims_with(queries=["Two Words", "two  words"]), "claim 1: duplicate query"),
        ([*CLAIMS[:1], {**CLAIMS[1], "claim": CLAIMS[0]["claim"].upper()}], "dupl"),
    ],
)
def test_main_exits_2_on_invalid_claims_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    claims: object,
    message: str,
) -> None:
    registry = FakeRegistry()

    assert run_main(monkeypatch, registry, tmp_path, claims) == 2

    assert registry.requested == []
    assert message in capsys.readouterr().err


def test_main_exits_2_on_a_claims_file_that_is_not_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claims = tmp_path / "claims.json"
    claims.write_text("[{", encoding="utf-8")
    assert main(["--log", str(tmp_path / "log.md"), str(claims)]) == 2
    assert "not JSON" in capsys.readouterr().err


def test_main_exits_2_on_an_oversized_claims_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(find_sources, "MAX_INPUT_BYTES", 10)
    claims = write_claims(tmp_path, CLAIMS)
    assert main(["--log", str(tmp_path / "log.md"), str(claims)]) == 2
    assert "over 10 bytes" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["claims", "log folder"])
def test_main_exits_2_when_a_path_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    claims = write_claims(tmp_path, CLAIMS)
    log = tmp_path / "source-search.md"
    if missing == "claims":
        claims = tmp_path / "absent.json"
    else:
        log = tmp_path / "absent" / "source-search.md"
    assert main(["--log", str(log), str(claims)]) == 2
    assert "absent" in capsys.readouterr().err


def test_main_exits_3_when_the_log_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "source-search.md").mkdir()

    assert run_main(monkeypatch, FakeRegistry(), tmp_path) == 3

    assert "cannot write log" in capsys.readouterr().err


def test_accepts_the_most_claims_allowed() -> None:
    claims = [
        {"claim": f"Claim {n}.", "queries": ["first words", "second words"]}
        for n in range(MAX_CLAIMS)
    ]
    assert len(find_sources.parse_claims(json.dumps(claims))) == MAX_CLAIMS
