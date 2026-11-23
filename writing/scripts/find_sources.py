"""Search the registries once for every claim of a piece of writing.

Usage:
    find_sources.py --log <folder>/source-search.md <claims.json>

The claims file is a JSON list of 1 to 20 claims, each an object with the
claim as one sentence and 2 to 4 queries of two to eight words:

    [{"claim": "The Ising model ...", "queries": ["...", "..."]}]

Every query goes to the OpenAlex search, four at a time, and each claim's
first query also goes to the arXiv search, one request every three seconds
alongside. At most five hits are kept from each answer. Hits print under their
claim, a work that several of the claim's requests found once and first, each
on one line: identifiers, year, title, the start of the abstract and the
requests that found it. Each claim prints at most its share of
MAX_PRINTED_CHARACTERS; the Markdown log holds the date, every request's URL
and outcome, and every hit.

Registry responses are kept for 24 hours in `sources.cache.json` beside the
log. No request starts after 120 s. Exits 0 when every request was answered,
1 when a registry was unavailable or sent a malformed answer or a request was
not started in time, 2 when the claims are invalid or a path is missing, and
3 when the log cannot be written.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# `python -I` leaves the script's own folder off sys.path, and its siblings sit in it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gap_search import (
    CACHE_NAME,
    MAX_RUN_SECONDS,
    Hit,
    Registry,
    Request,
    RequestOutcome,
    answer,
    arxiv_request,
    clean_text,
    hit_cells,
    merge_hits,
    normalise_query,
    openalex_request,
    problem_line,
)
from verify import Fetch, RegistryClient, ResponseCache

MAX_CLAIMS = 20
MIN_QUERIES = 2
MAX_QUERIES = 4
MAX_INPUT_BYTES = 100_000
MAX_OPENALEX_AT_ONCE = 4
MAX_PRINTED_CHARACTERS = 24_000


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    queries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimResult:
    claim: Claim
    requests: tuple[RequestOutcome, ...]
    hits: tuple[Hit, ...]


def parse_claims(text: str) -> tuple[Claim, ...]:
    """The claims of a claims file, cleaned.

    Raises ValueError naming the first problem: text that is not JSON, a
    count outside 1 to MAX_CLAIMS, a claim that is not an object with text and
    MIN_QUERIES to MAX_QUERIES queries, a query of the wrong length, or a
    repeated claim or query.
    """
    try:
        document = json.loads(text)
    except (ValueError, RecursionError) as err:
        raise ValueError(f"not JSON: {err}") from err
    if not isinstance(document, list) or not 1 <= len(document) <= MAX_CLAIMS:
        raise ValueError(f"expected a list of 1 to {MAX_CLAIMS} claims")
    claims = tuple(
        _claim(number, item) for number, item in enumerate(document, start=1)
    )
    seen: set[str] = set()
    for claim in claims:
        if claim.text.casefold() in seen:
            raise ValueError(f"duplicate claim {claim.text!r}")
        seen.add(claim.text.casefold())
    return claims


def _claim(number: int, item: object) -> Claim:
    if not isinstance(item, dict):
        raise ValueError(f"claim {number}: expected an object, got {item!r}")
    text = item.get("claim")
    if not isinstance(text, str) or not clean_text(text):
        raise ValueError(f"claim {number}: expected the claim as text")
    queries = item.get("queries")
    if (
        not isinstance(queries, list)
        or not MIN_QUERIES <= len(queries) <= MAX_QUERIES
        or not all(isinstance(query, str) for query in queries)
    ):
        raise ValueError(
            f"claim {number}: expected {MIN_QUERIES} to {MAX_QUERIES} queries as text"
        )
    try:
        cleaned = tuple(normalise_query(query) for query in queries)
    except ValueError as err:
        raise ValueError(f"claim {number}: {err}") from err
    folded = [query.casefold() for query in cleaned]
    if len(set(folded)) < len(folded):
        raise ValueError(f"claim {number}: duplicate query")
    return Claim(clean_text(text), cleaned)


def _claim_requests(claim: Claim) -> list[Request]:
    openalex = [
        openalex_request(number, query)
        for number, query in enumerate(claim.queries, start=1)
    ]
    return [*openalex, arxiv_request(1, claim.queries[0])]


def search_claims(
    claims: Sequence[Claim], fetch: Fetch, now: Callable[[], float] = time.monotonic
) -> tuple[ClaimResult, ...]:
    """Send every claim's requests, starting none after MAX_RUN_SECONDS.

    OpenAlex requests run MAX_OPENALEX_AT_ONCE at a time and arXiv requests
    one after another alongside, so arXiv's spacing never holds up OpenAlex.
    """
    deadline = now() + MAX_RUN_SECONDS
    per_claim = [_claim_requests(claim) for claim in claims]

    def send(request: Request) -> RequestOutcome:
        return answer(request, fetch, deadline, now)

    with (
        ThreadPoolExecutor(MAX_OPENALEX_AT_ONCE) as openalex_pool,
        ThreadPoolExecutor(1) as arxiv_lane,
    ):
        pending = [
            [
                (
                    arxiv_lane if request.registry is Registry.ARXIV else openalex_pool
                ).submit(send, request)
                for request in requests
            ]
            for requests in per_claim
        ]
        outcomes = [tuple(future.result() for future in futures) for futures in pending]
    return tuple(
        ClaimResult(claim, answered, _by_finders(merge_hits(answered)))
        for claim, answered in zip(claims, outcomes, strict=True)
    )


def _by_finders(hits: tuple[Hit, ...]) -> tuple[Hit, ...]:
    """A work several queries found comes first; ties keep the order found."""
    return tuple(sorted(hits, key=lambda hit: -len(hit.found_by)))


def _problem_line(number: int, outcome: RequestOutcome) -> str:
    return f"claim {number}, {problem_line(outcome)}"


def render_report(results: Sequence[ClaimResult], log: Path) -> str:
    """What the search prints: a summary, each failed request and each claim's hits.

    Each claim's lines stop before passing its share of MAX_PRINTED_CHARACTERS;
    the rest are only in the log.
    """
    outcomes = [(n, o) for n, r in enumerate(results, start=1) for o in r.requests]
    answered = sum(outcome.problem is None for _, outcome in outcomes)
    lines = [
        f"Answered {answered} of {len(outcomes)} requests for {len(results)} "
        f"claims. Log: {log}",
        *(_problem_line(n, outcome) for n, outcome in outcomes if outcome.problem),
    ]
    share = MAX_PRINTED_CHARACTERS // len(results)
    for number, result in enumerate(results, start=1):
        lines += ["", *_claim_lines(number, result, share)]
    return "\n".join(lines)


def _claim_lines(number: int, result: ClaimResult, share: int) -> list[str]:
    lines = [f"Claim {number}: {result.claim.text}"]
    size = len(lines[0]) + 1
    for printed, hit in enumerate(result.hits):
        line = " | ".join(hit_cells(hit))
        rest = f"{len(result.hits) - printed} more hits for this claim are in the log."
        if size + len(line) + 1 + len(rest) + 1 > share:
            lines.append(rest)
            break
        lines.append(line)
        size += len(line) + 1
    return lines


def render_log(results: Sequence[ClaimResult], searched: date) -> str:
    """The Markdown log of every claim's requests and hits."""
    lines = [
        "# Source search",
        "",
        f"Searched on {searched.isoformat()}. Each URL repeats its request.",
    ]
    for number, result in enumerate(results, start=1):
        lines += [
            "",
            f"## Claim {number}: {result.claim.text}",
            "",
            "| Request | Query | Outcome | URL |",
            "|---|---|---|---|",
        ]
        for outcome in result.requests:
            request = outcome.request
            status = outcome.problem or f"{outcome.hit_count} hits"
            lines.append(
                f"| {request.label} | {request.query} | {status} | {request.url} |"
            )
        lines += [
            "",
            "| Identifiers | Year | Title | Abstract, start | Found by |",
            "|---|---|---|---|---|",
            *("| " + " | ".join(hit_cells(hit)) + " |" for hit in result.hits),
        ]
    return "\n".join(lines) + "\n"


def _read_claims(path: Path) -> tuple[Claim, ...]:
    with path.open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError(f"over {MAX_INPUT_BYTES} bytes")
    return parse_claims(raw.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search OpenAlex and arXiv once for every claim's sources."
    )
    parser.add_argument(
        "--log", type=Path, required=True, metavar="PATH", help="Markdown log to write"
    )
    parser.add_argument("claims", type=Path, help="JSON list of claims and queries")
    args = parser.parse_args(argv)
    try:
        claims = _read_claims(args.claims)
    except (OSError, ValueError) as err:
        print(f"find_sources.py: cannot read {args.claims}: {err}", file=sys.stderr)
        return 2
    folder = args.log.parent
    if not folder.is_dir():
        print(f"find_sources.py: no folder {folder} for the log", file=sys.stderr)
        return 2
    # Titles and abstracts are UTF-8; a Windows console defaults to a legacy
    # code page that would fail on them.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    cache = ResponseCache(RegistryClient(), folder / CACHE_NAME)
    try:
        results = search_claims(claims, cache)
    finally:
        cache.save()
    print(render_report(results, args.log))
    try:
        args.log.write_text(render_log(results, date.today()), encoding="utf-8")
    except OSError as err:
        print(f"cannot write log {args.log}: {err}", file=sys.stderr)
        return 3
    failed = any(o.problem for result in results for o in result.requests)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover: entry point; main is tested directly
