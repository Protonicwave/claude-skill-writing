import io
import itertools
import json
import sys
import urllib.parse
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import gap_search
import pytest
from gap_search import MAX_RUN_SECONDS, main, search
from verify import RegistryUnavailableError

QUERIES = (
    "neural network sampler Ising model",
    "generative model Monte Carlo spin systems",
    "self-learning Monte Carlo",
)


def openalex(*works: dict[str, object]) -> bytes:
    return json.dumps({"meta": {"count": len(works)}, "results": list(works)}).encode()


def work(
    number: int,
    *,
    doi: str | None = None,
    title: str = "A neural sampler",
    abstract: str = "We train a network to propose spin configurations.",
    year: int = 2020,
) -> dict[str, object]:
    index = {word: [position] for position, word in enumerate(abstract.split())}
    return {
        "id": f"https://openalex.org/W{number}",
        "doi": None if doi is None else f"https://doi.org/{doi}",
        "title": title,
        "publication_year": year,
        "abstract_inverted_index": index,
    }


def arxiv_entry(
    arxiv_id: str,
    *,
    title: str = "A neural sampler",
    summary: str = "We train a network to propose spin configurations.",
    doi: str = "",
) -> str:
    published = f"<arxiv:doi>{doi}</arxiv:doi>" if doi else ""
    return f"""<entry>
    <id>http://arxiv.org/abs/{arxiv_id}</id>
    <published>2019-10-30T10:00:00Z</published>
    <title>{title}</title>
    <summary>{summary}</summary>
    {published}
  </entry>"""


def feed(*entries: str) -> bytes:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>{len(entries)}</opensearch:totalResults>
  {"".join(entries)}
</feed>""".encode()


EMPTY_FEED = feed()


class FakeRegistry:
    """Answers each URL from the first route whose fragment it contains.

    A route's answer is a body, None for HTTP 404, or an exception to raise.
    An unrouted URL fails the test, so every request a case makes is declared.
    """

    def __init__(self, routes: Sequence[tuple[str, bytes | Exception | None]]):
        self.routes = routes
        self.requested: list[str] = []

    def __call__(self, url: str) -> bytes | None:
        self.requested.append(url)
        for fragment, answer in self.routes:
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        pytest.fail(f"unexpected request {url}")


def no_hits() -> FakeRegistry:
    return FakeRegistry([("openalex", openalex()), ("arxiv", EMPTY_FEED)])


def run_main(
    monkeypatch: pytest.MonkeyPatch,
    registry: FakeRegistry,
    log: Path,
    queries: Sequence[str] = QUERIES,
) -> int:
    monkeypatch.setattr(gap_search, "RegistryClient", lambda: registry)
    return main(["--log", str(log), *queries])


def searched_words(url: str) -> tuple[str, str]:
    parts = urllib.parse.urlsplit(url)
    fields = urllib.parse.parse_qs(parts.query)
    if "search" in fields:
        return parts.hostname or "", fields["search"][0]
    terms = fields["search_query"][0].split(" AND ")
    return parts.hostname or "", " ".join(
        term.split(":")[1].strip('"') for term in terms
    )


def test_search_sends_each_query_once_to_each_registry() -> None:
    registry = no_hits()

    result = search(QUERIES, registry)

    assert sorted(searched_words(url) for url in registry.requested) == sorted(
        (host, query)
        for query in QUERIES
        for host in ("api.openalex.org", "export.arxiv.org")
    )
    assert [outcome.problem for outcome in result.requests] == [None] * 6


def test_search_lists_a_work_both_registries_return_once() -> None:
    registry = FakeRegistry(
        [
            ("openalex", openalex(work(1, doi="10.48550/arXiv.1910.13496"))),
            ("arxiv", feed(arxiv_entry("1910.13496v2"))),
        ]
    )

    result = search(QUERIES, registry)

    assert len(result.hits) == 1
    assert result.hits[0].arxiv == "1910.13496"
    assert result.hits[0].found_by == tuple(
        f"{name} q{number}" for number in (1, 2, 3) for name in ("OpenAlex", "arXiv")
    )


def test_search_joins_a_preprint_to_its_published_version() -> None:
    registry = FakeRegistry(
        [
            ("openalex", openalex(work(1, doi="10.1103/PhysRevE.101.023304"))),
            (
                "arxiv",
                feed(arxiv_entry("1910.13496v2", doi="10.1103/PhysRevE.101.023304")),
            ),
        ]
    )

    result = search(QUERIES, registry)

    assert [(hit.doi, hit.arxiv) for hit in result.hits] == [
        ("10.1103/physreve.101.023304", "1910.13496")
    ]


def test_search_keeps_at_most_five_hits_from_each_request() -> None:
    registry = FakeRegistry(
        [
            ("openalex", openalex(*(work(n) for n in range(7)))),
            ("arxiv", feed(*(arxiv_entry(f"2001.0000{n}") for n in range(7)))),
        ]
    )

    result = search(QUERIES, registry)

    assert [outcome.hit_count for outcome in result.requests] == [5] * 6
    assert len(result.hits) == 10


def test_search_starts_no_request_after_the_run_time_limit() -> None:
    registry = no_hits()
    clock = itertools.chain([0.0, 0.0, 0.0], itertools.repeat(MAX_RUN_SECONDS + 1))

    result = search(QUERIES, registry, now=lambda: next(clock))

    assert len(registry.requested) == 2
    problems = [outcome.problem or "" for outcome in result.requests]
    assert problems[:2] == ["", ""]
    assert all("not searched" in problem for problem in problems[2:])


def test_main_prints_each_hit_and_writes_the_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    filler = " ".join(f"word{n}" for n in range(100))
    abstract = f"We train a network | to propose spin\x07 configurations. {filler}"
    registry = FakeRegistry(
        [
            (
                "openalex",
                openalex(
                    work(
                        7,
                        doi="10.1103/PhysRevE.101.023304",
                        title="Neural\x1b samplers | Ising",
                        abstract=abstract,
                    )
                ),
            ),
            ("arxiv", EMPTY_FEED),
        ]
    )
    log = tmp_path / "gap-search.md"

    code = run_main(monkeypatch, registry, log)

    printed = capsys.readouterr().out
    hit_line = next(line for line in printed.splitlines() if "doi:" in line)
    assert code == 0
    assert hit_line.startswith(
        "doi:10.1103/physreve.101.023304 | 2020 | Neural samplers / Ising | "
    )
    assert "We train a network / to propose spin configurations." in hit_line
    assert "\x07" not in printed
    assert "\x1b" not in printed
    assert hit_line.endswith("... | OpenAlex q1, OpenAlex q2, OpenAlex q3")
    written = log.read_text(encoding="utf-8")
    assert date.today().isoformat() in written
    assert all(url in written for url in registry.requested)
    assert "Neural samplers / Ising" in written


@pytest.mark.parametrize(
    "routes",
    [
        [("openalex", None), ("arxiv", EMPTY_FEED)],
        [("openalex", openalex()), ("arxiv", EMPTY_FEED)],
    ],
    ids=["openalex-404", "empty-results"],
)
def test_main_exits_0_with_no_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    routes: list[tuple[str, bytes | None]],
) -> None:
    code = run_main(monkeypatch, FakeRegistry(routes), tmp_path / "gap-search.md")

    assert code == 0
    assert "0 hits" in capsys.readouterr().out


@pytest.mark.parametrize(
    "queries",
    [
        QUERIES[:2],
        (*QUERIES, "quantum annealing schedule"),
        ("sampler", *QUERIES[1:]),
        ("one two three four five six seven eight nine", *QUERIES[1:]),
        (QUERIES[0], "Neural  network sampler ISING model", QUERIES[2]),
    ],
    ids=["two-queries", "four-queries", "one-word", "nine-words", "duplicate"],
)
def test_main_exits_2_on_invalid_queries_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    queries: Sequence[str],
) -> None:
    registry = FakeRegistry([])

    code = run_main(monkeypatch, registry, tmp_path / "gap-search.md", queries)

    assert code == 2
    assert registry.requested == []
    assert "quer" in capsys.readouterr().err


def test_main_exits_2_when_the_log_folder_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = FakeRegistry([])
    missing = tmp_path / "absent"

    code = run_main(monkeypatch, registry, missing / "gap-search.md")

    assert code == 2
    assert registry.requested == []
    assert str(missing) in capsys.readouterr().err


@pytest.mark.parametrize(
    ("routes", "failed"),
    [
        (
            [
                ("openalex", openalex(work(1, title="Kept from OpenAlex"))),
                ("arxiv", RegistryUnavailableError("export.arxiv.org: HTTP 503")),
            ],
            "arXiv q1",
        ),
        (
            [
                ("openalex", b"<html>not JSON</html>"),
                ("arxiv", feed(arxiv_entry("2001.00001", title="Kept from arXiv"))),
            ],
            "OpenAlex q1",
        ),
        (
            [
                ("openalex", b'{"error": "bad request"}'),
                ("arxiv", feed(arxiv_entry("2001.00001", title="Kept from arXiv"))),
            ],
            "OpenAlex q1",
        ),
        (
            [
                ("openalex", openalex(work(1, title="Kept from OpenAlex"))),
                ("arxiv", b"<feed><entry>"),
            ],
            "arXiv q1",
        ),
        (
            [
                ("openalex", openalex(work(1, title="Kept from OpenAlex"))),
                ("arxiv", b"<html><body>Service unavailable</body></html>"),
            ],
            "arXiv q1",
        ),
        (
            [
                ("openalex", openalex(work(1, title="Kept from OpenAlex"))),
                (
                    "arxiv",
                    feed(arxiv_entry("api/errors#malformed_query", title="Error")),
                ),
            ],
            "arXiv q1",
        ),
    ],
    ids=[
        "unavailable",
        "not-json",
        "no-results",
        "broken-xml",
        "not-a-feed",
        "error-entry",
    ],
)
def test_main_exits_1_naming_a_failed_request_and_prints_the_other_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    routes: list[tuple[str, bytes | Exception]],
    failed: str,
) -> None:
    log = tmp_path / "gap-search.md"

    code = run_main(monkeypatch, FakeRegistry(routes), log)

    printed = capsys.readouterr().out
    assert code == 1
    assert f'{failed} "{QUERIES[0]}"' in printed
    assert "Kept from" in printed
    assert failed in log.read_text(encoding="utf-8")


def test_main_prints_at_most_its_character_limit_and_logs_every_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gap_search, "MAX_PRINTED_CHARACTERS", 1000)
    registry = FakeRegistry(
        [
            ("openalex", openalex(*(work(n, title=f"Work {n}") for n in range(5)))),
            (
                "arxiv",
                feed(
                    *(
                        arxiv_entry(f"2001.0000{n}", title=f"Paper {n}")
                        for n in range(5)
                    )
                ),
            ),
        ]
    )
    log = tmp_path / "gap-search.md"

    code = run_main(monkeypatch, registry, log)

    printed = capsys.readouterr().out
    assert code == 0
    assert len(printed) <= 1000
    assert "more hits are in the log" in printed
    written = log.read_text(encoding="utf-8")
    assert all(f"Work {n}" in written and f"Paper {n}" in written for n in range(5))


def test_main_rerun_answers_from_the_cache_beside_the_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "gap-search.md"
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert run_main(monkeypatch, no_hits(), log) == 0
    rerun = FakeRegistry([])

    assert run_main(monkeypatch, rerun, log) == 0
    assert rerun.requested == []
    assert (tmp_path / "sources.cache.json").is_file()


def test_main_writes_utf8_whatever_the_console_code_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    console = io.BytesIO()
    stdout = io.TextIOWrapper(console, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stdout)
    registry = FakeRegistry(
        [("openalex", openalex(work(1, title="Spin ψ sampler"))), ("arxiv", EMPTY_FEED)]
    )

    assert run_main(monkeypatch, registry, tmp_path / "gap-search.md") == 0
    stdout.flush()
    assert "Spin ψ sampler" in console.getvalue().decode("utf-8")


def test_main_exits_3_when_the_log_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "gap-search.md"
    log.mkdir()

    code = run_main(monkeypatch, no_hits(), log)

    assert code == 3
    assert str(log) in capsys.readouterr().err
