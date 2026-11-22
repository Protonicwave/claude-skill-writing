"""Search the registries once for published work that closes a stated gap.

Usage:
    gap_search.py --log <folder>/gap-search.md "<query 1>" "<query 2>" "<query 3>"

Each query, of two to eight words, goes once to the OpenAlex search and once to
the arXiv search, and at most five hits are kept from each answer. A work that
more than one request finds, or that both registries hold, as a preprint and
its published version for example, is listed once. Each hit prints on one line:
its identifiers, year, title, the start of its abstract and the requests that
found it. The log, in Markdown, holds the date, every request's URL and
outcome, and every hit, so the student can repeat the search.

Registry responses are kept for 24 hours in `sources.cache.json` beside the
log, the cache `verify.py` keeps for a sources file of that name. No request
starts after 120 s. Exits 0 when every request was answered, 1 when a registry
was unavailable or sent a malformed answer or a request was not started in
time, 2 when the arguments are invalid, and 3 when the log cannot be written.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import unicodedata
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

# `python -I` leaves the script's own folder off sys.path, and verify.py sits in it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify import (
    ATOM,
    ArxivId,
    Fetch,
    RegistryClient,
    RegistryUnavailableError,
    ResponseCache,
    from_inverted_index,
    parse_arxiv_entry,
    parse_identifier,
)

QUERY_COUNT = 3
MIN_QUERY_WORDS = 2
MAX_QUERY_WORDS = 8
MAX_HITS_PER_REQUEST = 5
MAX_RUN_SECONDS = 120.0
MAX_TITLE_CHARACTERS = 200
MAX_ABSTRACT_CHARACTERS = 300
MAX_PRINTED_CHARACTERS = 12_000
CACHE_NAME = "sources.cache.json"
OPENALEX_SEARCH = (
    "https://api.openalex.org/works?select=id,doi,title,publication_year,"
    f"abstract_inverted_index&per-page={MAX_HITS_PER_REQUEST}&search="
)
ARXIV_SEARCH = (
    f"https://export.arxiv.org/api/query?max_results={MAX_HITS_PER_REQUEST}"
    "&search_query="
)
OPENALEX_ID_PREFIX = "https://openalex.org/"


class Registry(StrEnum):
    OPENALEX = "OpenAlex"
    ARXIV = "arXiv"


@dataclass(frozen=True, slots=True)
class Request:
    registry: Registry
    query_number: int
    query: str
    url: str

    @property
    def label(self) -> str:
        return f"{self.registry} q{self.query_number}"


@dataclass(frozen=True, slots=True)
class RequestOutcome:
    """What one request returned; `problem` is None when it was answered."""

    request: Request
    hit_count: int
    problem: str | None


@dataclass(frozen=True, slots=True)
class Hit:
    """One work, under every identifier the registries gave it."""

    doi: str | None
    arxiv: str | None
    openalex: str | None
    year: int | None
    title: str
    abstract: str
    found_by: tuple[str, ...]

    @property
    def keys(self) -> frozenset[str]:
        """Identifiers that mark another hit as the same work."""
        return frozenset(
            f"{kind}:{value}"
            for kind, value in (
                ("doi", self.doi),
                ("arxiv", self.arxiv),
                ("openalex", self.openalex),
            )
            if value
        )

    def merged(self, other: Hit) -> Hit:
        return Hit(
            doi=self.doi or other.doi,
            arxiv=self.arxiv or other.arxiv,
            openalex=self.openalex or other.openalex,
            year=self.year or other.year,
            title=self.title or other.title,
            abstract=max(self.abstract, other.abstract, key=len),
            found_by=self.found_by
            + tuple(label for label in other.found_by if label not in self.found_by),
        )


@dataclass(frozen=True, slots=True)
class SearchResult:
    requests: tuple[RequestOutcome, ...]
    hits: tuple[Hit, ...]


class MalformedAnswerError(Exception):
    """A registry answered with something other than search results."""


def normalise_queries(queries: Sequence[str]) -> tuple[str, ...]:
    """The queries with control characters and extra spaces removed.

    Raises ValueError naming the first query of the wrong length, a repeated
    query, or a count other than QUERY_COUNT.
    """
    if len(queries) != QUERY_COUNT:
        raise ValueError(f"expected {QUERY_COUNT} queries, got {len(queries)}")
    cleaned = tuple(clean_text(query) for query in queries)
    for query in cleaned:
        words = len(_search_words(query))
        if not MIN_QUERY_WORDS <= words <= MAX_QUERY_WORDS:
            raise ValueError(
                f"expected {MIN_QUERY_WORDS} to {MAX_QUERY_WORDS} words in each "
                f"query, got {words} in {query!r}"
            )
    folded = [query.casefold() for query in cleaned]
    for index, query in enumerate(folded):
        if query in folded[:index]:
            raise ValueError(f"duplicate query {cleaned[index]!r}")
    return cleaned


def _search_words(query: str) -> list[str]:
    """The words of a query that name something; quotes and bare dashes are not."""
    words = (word.replace('"', "") for word in query.split())
    return [word for word in words if any(char.isalnum() for char in word)]


def clean_text(text: str) -> str:
    """Text safe to print on one line and in a Markdown table cell.

    Control characters become spaces, other invisible characters are dropped,
    `|` becomes `/`, and runs of whitespace become one space.
    """
    visible = "".join(_visible(char) for char in text)
    return " ".join(visible.replace("|", "/").split())


def _visible(char: str) -> str:
    category = unicodedata.category(char)
    if category == "Cc":
        return " "
    return "" if category.startswith("C") else char


def search(
    queries: Sequence[str], fetch: Fetch, now: Callable[[], float] = time.monotonic
) -> SearchResult:
    """Send each query once to each registry, starting none after MAX_RUN_SECONDS."""
    deadline = now() + MAX_RUN_SECONDS
    outcomes: list[RequestOutcome] = []
    hits: list[Hit] = []
    for request in _requests(queries):
        if now() > deadline:
            problem = f"not searched: run time limit of {MAX_RUN_SECONDS:.0f} s reached"
            outcomes.append(RequestOutcome(request, 0, problem))
            continue
        try:
            found = _ask(request, fetch)
        except RegistryUnavailableError as err:
            outcomes.append(RequestOutcome(request, 0, f"unavailable ({err})"))
            continue
        except MalformedAnswerError as err:
            outcomes.append(RequestOutcome(request, 0, f"malformed answer ({err})"))
            continue
        outcomes.append(RequestOutcome(request, len(found), None))
        for hit in found:
            _add(hits, hit)
    return SearchResult(tuple(outcomes), tuple(hits))


def _requests(queries: Sequence[str]) -> list[Request]:
    requests: list[Request] = []
    for number, query in enumerate(queries, start=1):
        # Each word must appear, which keeps arXiv's answers on the topic;
        # quoting keeps a hyphenated word together.
        arxiv_query = " AND ".join(f'all:"{word}"' for word in _search_words(query))
        requests.append(
            Request(
                Registry.OPENALEX,
                number,
                query,
                OPENALEX_SEARCH + urllib.parse.quote(query, safe=""),
            )
        )
        requests.append(
            Request(
                Registry.ARXIV,
                number,
                query,
                ARXIV_SEARCH + urllib.parse.quote(arxiv_query, safe=":"),
            )
        )
    return requests


def _ask(request: Request, fetch: Fetch) -> list[Hit]:
    body = fetch(request.url)
    if body is None:
        # A search address never has a legitimate 404: the registry moved it.
        raise RegistryUnavailableError(f"{request.url}: HTTP 404")
    if request.registry is Registry.OPENALEX:
        return _openalex_hits(body, request.label)
    return _arxiv_hits(body, request.label)


def _add(hits: list[Hit], found: Hit) -> None:
    joined = [index for index, hit in enumerate(hits) if hit.keys & found.keys]
    if not joined:
        hits.append(found)
        return
    merged = hits[joined[0]]
    for index in joined[1:]:
        merged = merged.merged(hits[index])
    hits[joined[0]] = merged.merged(found)
    for index in reversed(joined[1:]):
        del hits[index]


def _openalex_hits(body: bytes, label: str) -> list[Hit]:
    try:
        document = json.loads(body)
    except (ValueError, RecursionError) as err:
        raise MalformedAnswerError(f"not JSON: {err}") from err
    results = document.get("results") if isinstance(document, dict) else None
    if not isinstance(results, list):
        raise MalformedAnswerError("no list of results")
    return [
        _openalex_hit(work, label)
        for work in results[:MAX_HITS_PER_REQUEST]
        if isinstance(work, dict)
    ]


def _openalex_hit(work: dict[str, Any], label: str) -> Hit:
    doi, arxiv = _doi_or_arxiv(work.get("doi"))
    raw_id = work.get("id")
    openalex = (
        raw_id.removeprefix(OPENALEX_ID_PREFIX) if isinstance(raw_id, str) else None
    )
    year = work.get("publication_year")
    title = work.get("title")
    return Hit(
        doi=doi,
        arxiv=arxiv,
        openalex=openalex,
        year=year if isinstance(year, int) and not isinstance(year, bool) else None,
        title=clean_text(title) if isinstance(title, str) else "",
        abstract=clean_text(from_inverted_index(work.get("abstract_inverted_index"))),
        found_by=(label,),
    )


def _doi_or_arxiv(raw: object) -> tuple[str | None, str | None]:
    if not isinstance(raw, str):
        return None, None
    try:
        identifier = parse_identifier(raw)
    except ValueError:
        return None, None
    if isinstance(identifier, ArxivId):
        return None, identifier.base
    return identifier, None


def _arxiv_hits(body: bytes, label: str) -> list[Hit]:
    try:
        # The answer comes from arXiv over https; expat in Python 3.12 refuses
        # entity expansion attacks and ElementTree resolves no external entities.
        feed = ElementTree.fromstring(body)  # noqa: S314
    except ElementTree.ParseError as err:
        raise MalformedAnswerError(f"unreadable feed: {err}") from err
    if feed.tag != f"{ATOM}feed":
        raise MalformedAnswerError(f"expected an Atom feed, got <{feed.tag}>")
    return [
        _arxiv_hit(entry, label)
        for entry in feed.findall(f"{ATOM}entry")[:MAX_HITS_PER_REQUEST]
    ]


def _arxiv_hit(entry: ElementTree.Element, label: str) -> Hit:
    raw_id = entry.findtext(f"{ATOM}id", "")
    _, arxiv = _doi_or_arxiv(raw_id)
    if arxiv is None:
        # arXiv reports a bad query as an entry whose id is an error page.
        summary = clean_text(entry.findtext(f"{ATOM}summary", ""))
        raise MalformedAnswerError(f"entry {raw_id!r} is not a paper: {summary}")
    parsed = parse_arxiv_entry(entry)
    journal_doi, _ = _doi_or_arxiv(parsed.doi)
    return Hit(
        doi=journal_doi,
        arxiv=arxiv,
        openalex=None,
        year=parsed.published_year,
        title=clean_text(parsed.title),
        abstract=clean_text(parsed.summary),
        found_by=(label,),
    )


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def _identifiers(hit: Hit) -> str:
    names = [f"doi:{hit.doi}"] if hit.doi else []
    names += [f"arXiv:{hit.arxiv}"] if hit.arxiv else []
    return " ".join(names) or f"OpenAlex:{hit.openalex}"


def _hit_cells(hit: Hit) -> tuple[str, ...]:
    return (
        _identifiers(hit),
        "no year" if hit.year is None else str(hit.year),
        _trim(hit.title, MAX_TITLE_CHARACTERS) or "no title",
        _trim(hit.abstract, MAX_ABSTRACT_CHARACTERS) or "no abstract",
        ", ".join(hit.found_by),
    )


def _problem_line(outcome: RequestOutcome) -> str:
    request = outcome.request
    return f'{request.label} "{request.query}": {outcome.problem}'


def render_report(result: SearchResult, log: Path) -> str:
    """What the search prints: a summary, each failed request and each hit.

    Hit lines stop before the output passes MAX_PRINTED_CHARACTERS; the rest
    are only in the log.
    """
    answered = sum(outcome.problem is None for outcome in result.requests)
    lines = [
        f"Answered {answered} of {len(result.requests)} requests; "
        f"{len(result.hits)} hits. Log: {log}",
        *(_problem_line(outcome) for outcome in result.requests if outcome.problem),
        "",
    ]
    size = sum(len(line) + 1 for line in lines)
    for printed, hit in enumerate(result.hits):
        line = " | ".join(_hit_cells(hit))
        rest = f"{len(result.hits) - printed} more hits are in the log."
        if size + len(line) + 1 + len(rest) + 1 > MAX_PRINTED_CHARACTERS:
            lines.append(rest)
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines)


def render_log(queries: Sequence[str], result: SearchResult, searched: date) -> str:
    """The Markdown log of every request and every hit."""
    lines = [
        "# Gap search",
        "",
        f"Searched on {searched.isoformat()}. Each URL repeats its request.",
        "",
        "## Queries",
        "",
        *(f"{number}. {query}" for number, query in enumerate(queries, start=1)),
        "",
        "## Requests",
        "",
        "| Request | Outcome | URL |",
        "|---|---|---|",
    ]
    for outcome in result.requests:
        status = outcome.problem or f"{outcome.hit_count} hits"
        lines.append(f"| {outcome.request.label} | {status} | {outcome.request.url} |")
    lines += [
        "",
        "## Hits",
        "",
        "| Identifiers | Year | Title | Abstract, first "
        f"{MAX_ABSTRACT_CHARACTERS} characters | Found by |",
        "|---|---|---|---|---|",
        *("| " + " | ".join(_hit_cells(hit)) + " |" for hit in result.hits),
    ]
    return "\n".join(lines) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search OpenAlex and arXiv once for work that closes a gap."
    )
    parser.add_argument(
        "--log", type=Path, required=True, metavar="PATH", help="Markdown log to write"
    )
    parser.add_argument(
        "queries", nargs="*", help=f"{QUERY_COUNT} queries of 2 to 8 words"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        queries = normalise_queries(args.queries)
    except ValueError as err:
        print(f"gap_search.py: {err}", file=sys.stderr)
        return 2
    folder = args.log.parent
    if not folder.is_dir():
        print(f"gap_search.py: no folder {folder} for the log", file=sys.stderr)
        return 2
    # Titles and abstracts are UTF-8; a Windows console defaults to a legacy
    # code page that would fail on them.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    cache = ResponseCache(RegistryClient(), folder / CACHE_NAME)
    try:
        result = search(queries, cache)
    finally:
        cache.save()
    print(render_report(result, args.log))
    try:
        args.log.write_text(render_log(queries, result, date.today()), encoding="utf-8")
    except OSError as err:
        print(f"cannot write log {args.log}: {err}", file=sys.stderr)
        return 3
    return 0 if all(outcome.problem is None for outcome in result.requests) else 1


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover: entry point; main is tested directly
