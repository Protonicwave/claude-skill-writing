"""Check cited references and quoted passages against scholarly registries.

Usage:
    verify.py <sources.jsonl>
    verify.py -               read the sources from standard input

Each line of the input is one source as the draft cites it:

    {"key": "Feynman1982", "id": "10.1007/BF02650179",
     "title": "Simulating physics with computers", "authors": ["Feynman"],
     "year": 1982, "volume": "21", "pages": "467-488",
     "evidence": [{"claim": "...", "quote": "...", "text": "feynman.html"}]}

`id` is a DOI or an arXiv identifier in any usual form. `authors` lists
surnames in order; a final "et al." stands for the rest. `volume` and `pages`
are optional. Each quote must appear word for word in the registry abstract
or, when `text` names one, in a saved copy of the full text (plain text or
HTML, relative to the input file).

Prints the verification log as a Markdown table. Exits 0 if every source is
verified, 1 if any is not, 2 if the input cannot be read or is invalid.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, NewType
from xml.etree import ElementTree

MAX_SOURCES = 50
MAX_INPUT_CHARACTERS = 2_000_000
MAX_EVIDENCE_PER_SOURCE = 20
# A quote short enough to be a bare number carries no context to check.
MIN_QUOTE_CHARACTERS = 20
MAX_QUOTE_CHARACTERS = 2000
MAX_TEXT_FILE_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2.0
MAX_RETRY_WAIT_SECONDS = 30.0
# arXiv asks for one request every three seconds.
ARXIV_INTERVAL_SECONDS = 3.0
EARLIEST_YEAR = 1600
USER_AGENT = "writing-skill-verify/0.1"

CROSSREF_WORKS = "https://api.crossref.org/works/"
OPENALEX_WORKS = "https://api.openalex.org/works/doi:"
OPENALEX_FIELDS = "?select=is_retracted,abstract_inverted_index"
ARXIV_QUERY = "https://export.arxiv.org/api/query?id_list="
ARXIV_HOST = "export.arxiv.org"
ARXIV_DOI_PREFIX = "10.48550/arxiv."

_HTTP_NOT_FOUND = 404
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
# Crossref notice types after which the work must not be cited for its content.
_RETRACTING_NOTICES = frozenset({"retraction", "withdrawal", "removal"})
_ET_AL = re.compile(r"^et\.?\s+al\.?$", re.IGNORECASE)
_RETRACTED_TITLE_PREFIX = re.compile(
    r"^\s*retracted(?: article)?\s*:\s*", re.IGNORECASE
)
_DOI_PREFIX = re.compile(
    r"^(?:doi:\s*|(?:https?://)?(?:dx\.)?doi\.org/)", re.IGNORECASE
)
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_ARXIV_PREFIX = re.compile(
    r"^(?:arxiv:\s*|(?:https?://)?(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|html)/)",
    re.IGNORECASE,
)
_ARXIV = re.compile(
    r"^(?P<base>\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v(?P<version>\d+))?$",
    re.IGNORECASE,
)
_ARXIV_VERSION = re.compile(r"v(\d+)$")
_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[\W_]+")
_TYPOGRAPHY = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00ad": None,
    }
)
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"
_OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"


# Identifiers

Doi = NewType("Doi", str)


@dataclass(frozen=True, slots=True)
class ArxivId:
    """An arXiv identifier, new style (`1706.03762`) or old (`hep-th/9711200`)."""

    base: str
    version: int | None

    def __str__(self) -> str:
        return self.base if self.version is None else f"{self.base}v{self.version}"


type Identifier = Doi | ArxivId


def parse_identifier(raw: str) -> Identifier:
    text = raw.strip()
    doi = _DOI_PREFIX.sub("", text).lower()
    if doi.startswith(ARXIV_DOI_PREFIX):
        text = doi.removeprefix(ARXIV_DOI_PREFIX)
    arxiv = _ARXIV.match(_ARXIV_PREFIX.sub("", text).removesuffix(".pdf"))
    if arxiv:
        version = arxiv["version"]
        return ArxivId(arxiv["base"].lower(), int(version) if version else None)
    if _DOI.match(doi):
        return Doi(doi)
    raise ValueError(f"expected a DOI or arXiv identifier, got {raw!r}")


def identifier_label(identifier: Identifier) -> str:
    if isinstance(identifier, ArxivId):
        return f"arXiv:{identifier}"
    return f"doi:{identifier}"


# Text


class _VisibleText(HTMLParser):
    """The text a reader sees in HTML or JATS markup, without scripts or styles."""

    _HIDDEN = frozenset({"script", "style", "noscript", "head", "template"})
    _BLOCKS = frozenset(
        {
            "p",
            "div",
            "br",
            "li",
            "tr",
            "td",
            "th",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "section",
            "article",
            "table",
            "figcaption",
            "blockquote",
            "jats:p",
            "jats:title",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._HIDDEN:
            self._hidden_depth += 1
        elif tag in self._BLOCKS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._HIDDEN:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        elif tag in self._BLOCKS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            self.parts.append(data)


def visible_text(markup: str) -> str:
    parser = _VisibleText()
    parser.feed(markup)
    parser.close()
    return "".join(parser.parts)


def normalise_passage(text: str) -> str:
    """Text as a quote is matched: case and words kept, typography folded.

    Copying from a PDF or web page changes ligatures, quote marks, minus
    signs and line breaks, none of which change what the passage says.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY)
    return _WHITESPACE.sub(" ", folded).strip()


def _comparable(text: str) -> str:
    """Text as titles and names are compared: case, accents and punctuation dropped."""
    decomposed = unicodedata.normalize("NFKD", visible_text(text))
    letters = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", letters.casefold()).strip()


# Input


@dataclass(frozen=True, slots=True)
class Evidence:
    claim: str
    quote: str
    text_name: str | None
    saved_text: str | None


@dataclass(frozen=True, slots=True)
class CitedSource:
    key: str
    identifier: Identifier
    title: str
    authors: tuple[str, ...]
    has_more_authors: bool
    year: int
    volume: str | None
    pages: str | None
    evidence: tuple[Evidence, ...]


def parse_sources(text: str, base_dir: Path) -> list[CitedSource]:
    """Parse JSON Lines of cited sources. Raises ValueError naming the line."""
    parsed: list[CitedSource] = []
    keys: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            source = _parse_source(line, base_dir)
        except ValueError as err:
            raise ValueError(f"line {number}: {err}") from err
        if source.key in keys:
            raise ValueError(f"line {number}: duplicate key {source.key!r}")
        keys.add(source.key)
        parsed.append(source)
        if len(parsed) > MAX_SOURCES:
            raise ValueError(
                f"more than {MAX_SOURCES} sources; a search this size needs a "
                "systematic review, not a spot check"
            )
    if not parsed:
        raise ValueError("no sources in the input")
    return parsed


def _parse_source(line: str, base_dir: Path) -> CitedSource:
    entry = json.loads(line)
    if not isinstance(entry, dict):
        raise ValueError(f"expected an object, got {type(entry).__name__}")
    authors, has_more = _authors(entry.get("authors"))
    return CitedSource(
        key=_required_text(entry, "key"),
        identifier=parse_identifier(_required_text(entry, "id")),
        title=_required_text(entry, "title"),
        authors=authors,
        has_more_authors=has_more,
        year=_year(entry.get("year")),
        volume=_optional_text(entry, "volume"),
        pages=_optional_text(entry, "pages"),
        evidence=_evidence(entry.get("evidence"), base_dir),
    )


def _required_text(entry: dict[str, Any], name: str) -> str:
    value = entry.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"field {name!r} must be a non-empty string")
    return value.strip()


def _optional_text(entry: dict[str, Any], name: str) -> str | None:
    value = entry.get(name)
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _required_text(entry, name)


def _year(value: object) -> int:
    latest = date.today().year + 1
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not EARLIEST_YEAR <= value <= latest
    ):
        raise ValueError(f"field 'year' must be a year as a number, got {value!r}")
    return value


def _authors(value: object) -> tuple[tuple[str, ...], bool]:
    if not isinstance(value, list) or not all(
        isinstance(name, str) and name.strip() for name in value
    ):
        raise ValueError("field 'authors' must be a list of surnames")
    names = [name.strip() for name in value]
    has_more = bool(names) and bool(_ET_AL.match(names[-1]))
    surnames = tuple(names[:-1] if has_more else names)
    if not surnames:
        raise ValueError("field 'authors' must name at least one author")
    return surnames, has_more


def _evidence(value: object, base_dir: Path) -> tuple[Evidence, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_EVIDENCE_PER_SOURCE:
        raise ValueError(
            f"field 'evidence' must list 1 to {MAX_EVIDENCE_PER_SOURCE} claims"
        )
    items = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each evidence item must be an object")
        quote = normalise_passage(_required_text(item, "quote"))
        if not MIN_QUOTE_CHARACTERS <= len(quote) <= MAX_QUOTE_CHARACTERS:
            raise ValueError(
                f"each quote must be at least {MIN_QUOTE_CHARACTERS} and at most "
                f"{MAX_QUOTE_CHARACTERS} characters, got {len(quote)}"
            )
        text_name = _optional_text(item, "text")
        saved = None if text_name is None else _read_saved_text(base_dir / text_name)
        items.append(Evidence(_required_text(item, "claim"), quote, text_name, saved))
    return tuple(items)


def _read_saved_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            raise ValueError(
                f"text file {path.name} is over {MAX_TEXT_FILE_BYTES} bytes"
            )
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        raise ValueError(f"cannot read text file {path.name}: {err.strerror}") from err
    if path.suffix.lower() in {".html", ".htm", ".xhtml"}:
        raw = visible_text(raw)
    return normalise_passage(raw)


# Registry access


type Fetch = Callable[[str], bytes | None]


class RegistryUnavailableError(Exception):
    """A registry could not answer: rate limited, down, unreachable or oversized."""


class RegistryClient:
    """Fetches registry URLs with bounded retries and arXiv's request spacing.

    Returns the body, or None for HTTP 404. Raises RegistryUnavailableError
    when the registry cannot answer within MAX_ATTEMPTS.
    """

    def __init__(self) -> None:
        self._last_arxiv_request = -math.inf

    def __call__(self, url: str) -> bytes | None:
        host = urllib.parse.urlsplit(url).hostname or url
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._space_arxiv(host)
            try:
                return _get(url)
            except urllib.error.HTTPError as err:
                if err.code == _HTTP_NOT_FOUND:
                    return None
                if err.code not in _RETRYABLE_STATUSES or attempt == MAX_ATTEMPTS:
                    raise RegistryUnavailableError(f"{host}: HTTP {err.code}") from err
                time.sleep(_retry_wait(err.headers.get("Retry-After"), attempt))
            except OSError as err:
                if attempt == MAX_ATTEMPTS:
                    raise RegistryUnavailableError(f"{host}: {err}") from err
                time.sleep(_retry_wait(None, attempt))
        raise AssertionError("the retry loop returns or raises on its last attempt")

    def _space_arxiv(self, host: str) -> None:
        if host != ARXIV_HOST:
            return
        wait = self._last_arxiv_request + ARXIV_INTERVAL_SECONDS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_arxiv_request = time.monotonic()


def _get(url: str) -> bytes:
    # Every URL is built from the https registry constants above.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
        body: bytes = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise RegistryUnavailableError(f"response over {MAX_RESPONSE_BYTES} bytes")
    return body


def _retry_wait(retry_after: str | None, attempt: int) -> float:
    if retry_after is not None and retry_after.strip().isdigit():
        return min(float(retry_after), MAX_RETRY_WAIT_SECONDS)
    return min(BACKOFF_BASE_SECONDS**attempt, MAX_RETRY_WAIT_SECONDS)


# Records


@dataclass(frozen=True, slots=True)
class Notice:
    kind: str
    retracts: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Record:
    query_url: str
    titles: tuple[str, ...]
    authors: tuple[str, ...]
    years: tuple[int, ...]
    venue: str
    volume: str | None
    first_page: str | None
    texts: tuple[tuple[str, str], ...]
    notices: tuple[Notice, ...]
    retraction_checked: str
    version: str


@dataclass(frozen=True, slots=True)
class Missing:
    query_url: str
    reason: str


def look_up(identifier: Identifier, fetch: Fetch) -> Record | Missing:
    if isinstance(identifier, ArxivId):
        return _look_up_arxiv(identifier, fetch)
    return _look_up_doi(identifier, fetch)


def _look_up_doi(doi: Doi, fetch: Fetch) -> Record | Missing:
    quoted = urllib.parse.quote(doi, safe="/")
    url = CROSSREF_WORKS + quoted
    try:
        body = fetch(url)
    except RegistryUnavailableError as err:
        return Missing(url, f"Crossref unavailable ({err})")
    if body is None:
        return Missing(url, "no Crossref record for this DOI")
    try:
        work = json.loads(body)["message"]
        record = _crossref_record(url, work)
    except (ValueError, KeyError, TypeError) as err:
        return Missing(url, f"Crossref returned an unreadable record ({err!r})")
    return _with_openalex(record, OPENALEX_WORKS + quoted + OPENALEX_FIELDS, fetch)


def _crossref_record(url: str, work: dict[str, Any]) -> Record:
    title = _first(work.get("title"))
    subtitle = _first(work.get("subtitle"))
    titles = (title, f"{title} {subtitle}") if subtitle else (title,)
    authors = tuple(
        str(author.get("family") or author.get("name") or "")
        for author in work.get("author") or []
        if isinstance(author, dict)
    )
    years = tuple(
        dict.fromkeys(
            int(work[name]["date-parts"][0][0])
            for name in ("issued", "published-print", "published-online")
            if isinstance(work.get(name), dict)
        )
    )
    page = work.get("page")
    first_page = str(page).split("-")[0] if page else work.get("article-number")
    abstract = work.get("abstract")
    texts = (
        (("abstract (Crossref)", normalise_passage(visible_text(abstract))),)
        if abstract
        else ()
    )
    return Record(
        query_url=url,
        titles=titles,
        authors=authors,
        years=years,
        venue=_first(work.get("container-title")),
        volume=str(work["volume"]) if work.get("volume") else None,
        first_page=str(first_page) if first_page else None,
        texts=texts,
        notices=_crossref_notices(work.get("updated-by") or []),
        retraction_checked="Crossref",
        version="version of record",
    )


def _crossref_notices(updates: list[Any]) -> tuple[Notice, ...]:
    notices: dict[tuple[str, str], Notice] = {}
    for update in updates:
        if not isinstance(update, dict):
            continue
        kind = str(update.get("type", "update"))
        notice_doi = str(update.get("DOI", ""))
        parts = (update.get("updated") or {}).get("date-parts") or [[]]
        when = "-".join(f"{part:02d}" for part in parts[0])
        label = update.get("label") or kind
        notices.setdefault(
            (kind, notice_doi),
            Notice(
                kind, kind in _RETRACTING_NOTICES, f"{label} doi:{notice_doi} ({when})"
            ),
        )
    return tuple(notices.values())


def _with_openalex(record: Record, url: str, fetch: Fetch) -> Record:
    try:
        body = fetch(url)
        work = json.loads(body) if body is not None else None
    except RegistryUnavailableError as err:
        return replace(
            record, retraction_checked=f"Crossref; OpenAlex unavailable ({err})"
        )
    except ValueError:
        return replace(
            record, retraction_checked="Crossref; OpenAlex record unreadable"
        )
    if not isinstance(work, dict):
        return replace(record, retraction_checked="Crossref; no OpenAlex record")
    notices = record.notices
    if work.get("is_retracted") is True:
        notices += (Notice("retracted", True, "OpenAlex marks it retracted"),)
    texts = record.texts
    abstract = _from_inverted_index(work.get("abstract_inverted_index"))
    if abstract:
        texts += (("abstract (OpenAlex)", normalise_passage(abstract)),)
    return replace(
        record, notices=notices, texts=texts, retraction_checked="Crossref and OpenAlex"
    )


def _from_inverted_index(index: object) -> str:
    if not isinstance(index, dict):
        return ""
    placed = sorted(
        (position, word)
        for word, positions in index.items()
        if isinstance(positions, list)
        for position in positions
        if isinstance(position, int)
    )
    return " ".join(word for _, word in placed)


def _first(value: object) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value) if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class _ArxivEntry:
    version: int
    title: str
    authors: tuple[str, ...]
    published_year: int
    updated_year: int
    summary: str
    comment: str
    journal_ref: str
    doi: str


def _look_up_arxiv(arxiv: ArxivId, fetch: Fetch) -> Record | Missing:
    latest_url = ARXIV_QUERY + arxiv.base
    latest = _arxiv_entry(latest_url, fetch)
    if isinstance(latest, Missing):
        return latest
    cited, url = latest, latest_url
    if arxiv.version is not None and arxiv.version != latest.version:
        url = ARXIV_QUERY + str(arxiv)
        older = _arxiv_entry(url, fetch)
        if isinstance(older, Missing):
            return older
        cited = older
    return _arxiv_record(url, cited, latest)


def _arxiv_entry(url: str, fetch: Fetch) -> _ArxivEntry | Missing:
    try:
        body = fetch(url)
    except RegistryUnavailableError as err:
        return Missing(url, f"arXiv unavailable ({err})")
    if body is None:
        return Missing(url, "no arXiv paper with this identifier")
    try:
        # The response comes from arXiv over https; expat in Python 3.12
        # refuses entity expansion attacks and ElementTree resolves no
        # external entities.
        feed = ElementTree.fromstring(body)  # noqa: S314
    except ElementTree.ParseError as err:
        return Missing(url, f"arXiv returned an unreadable feed ({err})")
    entry = feed.find(f"{_ATOM}entry")
    if feed.findtext(f"{_OPENSEARCH}totalResults", "0").strip() == "0" or entry is None:
        return Missing(url, "no arXiv paper with this identifier")
    return _parse_arxiv_entry(entry)


def _parse_arxiv_entry(entry: ElementTree.Element) -> _ArxivEntry:
    def text(tag: str) -> str:
        return _WHITESPACE.sub(" ", entry.findtext(tag, "")).strip()

    version = _ARXIV_VERSION.search(text(f"{_ATOM}id"))
    return _ArxivEntry(
        version=int(version.group(1)) if version else 1,
        title=text(f"{_ATOM}title"),
        authors=tuple(
            _WHITESPACE.sub(" ", author.findtext(f"{_ATOM}name", "")).strip()
            for author in entry.findall(f"{_ATOM}author")
        ),
        published_year=int(text(f"{_ATOM}published")[:4] or 0),
        updated_year=int(text(f"{_ATOM}updated")[:4] or 0),
        summary=text(f"{_ATOM}summary"),
        comment=text(f"{_ARXIV_NS}comment"),
        journal_ref=text(f"{_ARXIV_NS}journal_ref"),
        doi=text(f"{_ARXIV_NS}doi"),
    )


def _arxiv_record(url: str, cited: _ArxivEntry, latest: _ArxivEntry) -> Record:
    if cited.version == latest.version:
        version = f"v{cited.version} (latest)"
    else:
        version = (
            f"cited v{cited.version}; latest is v{latest.version}, "
            "check quoted figures still hold"
        )
    published = ", ".join(
        part
        for part in (latest.journal_ref, latest.doi and f"doi:{latest.doi}")
        if part
    )
    if published:
        version += f"; published as {published}, cite that version"
    notices: tuple[Notice, ...] = ()
    if "withdrawn" in latest.comment.casefold():
        notices = (
            Notice("withdrawn", True, f"arXiv v{latest.version}: {latest.comment}"),
        )
    return Record(
        query_url=url,
        titles=(cited.title,),
        authors=cited.authors,
        years=tuple(dict.fromkeys((cited.published_year, cited.updated_year))),
        venue="arXiv",
        volume=None,
        first_page=None,
        texts=(
            (f"abstract (arXiv v{cited.version})", normalise_passage(cited.summary)),
        ),
        notices=notices,
        retraction_checked="arXiv comments",
        version=version,
    )


# Comparison


class Outcome(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    NOT_GIVEN = "not given"
    NOT_IN_RECORD = "not in record"


class Status(StrEnum):
    VERIFIED = "VERIFIED"
    CLAIM_NOT_CHECKED = "CLAIM NOT CHECKED"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "UNVERIFIED"
    RETRACTED = "RETRACTED"


@dataclass(frozen=True, slots=True)
class FieldCheck:
    field: str
    outcome: Outcome
    detail: str


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    claim: str
    found_in: str | None


@dataclass(frozen=True, slots=True)
class Verification:
    source: CitedSource
    status: Status
    query_url: str
    reason: str
    venue: str
    version: str
    fields: tuple[FieldCheck, ...]
    claims: tuple[ClaimCheck, ...]
    notices: tuple[Notice, ...]
    retraction_checked: str


def verify(source: CitedSource, fetch: Fetch) -> Verification:
    lookup = look_up(source.identifier, fetch)
    if isinstance(lookup, Missing):
        return Verification(
            source,
            Status.UNVERIFIED,
            lookup.query_url,
            lookup.reason,
            "",
            "",
            (),
            (),
            (),
            "not checked",
        )
    fields = compare_fields(source, lookup)
    claims = tuple(
        ClaimCheck(evidence.claim, _find_quote(evidence, lookup))
        for evidence in source.evidence
    )
    return Verification(
        source,
        _status(fields, claims, lookup),
        lookup.query_url,
        "",
        lookup.venue,
        lookup.version,
        fields,
        claims,
        lookup.notices,
        lookup.retraction_checked,
    )


def compare_fields(source: CitedSource, record: Record) -> tuple[FieldCheck, ...]:
    return (
        _check_title(source.title, record.titles),
        _check_authors(source, record.authors),
        _check_year(source.year, record.years),
        _check_optional("volume", source.volume, record.volume),
        _check_optional(
            "first page",
            source.pages.split("-")[0].strip() if source.pages else None,
            record.first_page,
        ),
    )


def _check_title(cited: str, titles: tuple[str, ...]) -> FieldCheck:
    wanted = _comparable(cited)
    if any(_comparable(_RETRACTED_TITLE_PREFIX.sub("", t)) == wanted for t in titles):
        return FieldCheck("title", Outcome.MATCH, "")
    return FieldCheck("title", Outcome.MISMATCH, f"record has {titles[0]!r}")


def _check_authors(source: CitedSource, recorded: tuple[str, ...]) -> FieldCheck:
    cited = source.authors
    if len(cited) > len(recorded) or (
        not source.has_more_authors and len(cited) != len(recorded)
    ):
        return FieldCheck(
            "authors",
            Outcome.MISMATCH,
            f"cited {len(cited)}{' or more' if source.has_more_authors else ''}, "
            f"record has {len(recorded)}",
        )
    for position, (surname, name) in enumerate(zip(cited, recorded, strict=False), 1):
        if not _is_surname_of(surname, name):
            return FieldCheck(
                "authors",
                Outcome.MISMATCH,
                f"author {position}: cited {surname}, record has {name}",
            )
    return FieldCheck("authors", Outcome.MATCH, "")


def _is_surname_of(surname: str, name: str) -> bool:
    wanted, full = _comparable(surname), _comparable(name)
    return bool(wanted) and (full == wanted or full.endswith(f" {wanted}"))


def _check_year(cited: int, years: tuple[int, ...]) -> FieldCheck:
    others = ", ".join(str(year) for year in years if year != cited)
    if cited in years:
        return FieldCheck(
            "year", Outcome.MATCH, f"record also gives {others}" if others else ""
        )
    return FieldCheck("year", Outcome.MISMATCH, f"record gives {others}")


def _check_optional(name: str, cited: str | None, recorded: str | None) -> FieldCheck:
    if cited is None:
        return FieldCheck(name, Outcome.NOT_GIVEN, "")
    if recorded is None:
        return FieldCheck(name, Outcome.NOT_IN_RECORD, "")
    if cited.strip().casefold() == recorded.strip().casefold():
        return FieldCheck(name, Outcome.MATCH, "")
    return FieldCheck(name, Outcome.MISMATCH, f"record has {recorded}")


def _find_quote(evidence: Evidence, record: Record) -> str | None:
    for where, text in record.texts:
        if evidence.quote in text:
            return where
    if evidence.saved_text is not None and evidence.quote in evidence.saved_text:
        return f"saved text {evidence.text_name}"
    return None


def _status(
    fields: tuple[FieldCheck, ...], claims: tuple[ClaimCheck, ...], record: Record
) -> Status:
    if any(notice.retracts for notice in record.notices):
        return Status.RETRACTED
    if any(check.outcome is Outcome.MISMATCH for check in fields):
        return Status.MISMATCH
    if any(claim.found_in is None for claim in claims):
        return Status.CLAIM_NOT_CHECKED
    return Status.VERIFIED


# Log


_COLUMNS = (
    "Key",
    "Cited as",
    "Identifier",
    "Query URL",
    "Retrieved",
    "Title / authors / year / volume / first page",
    "Retraction",
    "Version",
    "Claims",
    "Status",
)


def render_log(verifications: Sequence[Verification], retrieved: date) -> str:
    """The verification log: a Markdown table, then a one-line count."""
    rows = [
        "| " + " | ".join(_COLUMNS) + " |",
        "|" + "---|" * len(_COLUMNS),
        *(_row(verification, retrieved) for verification in verifications),
    ]
    verified = sum(v.status is Status.VERIFIED for v in verifications)
    return (
        "\n".join(rows) + f"\n\n{verified} of {len(verifications)} sources verified.\n"
    )


def _row(verification: Verification, retrieved: date) -> str:
    source = verification.source
    cells = (
        source.key,
        _cited_as(source),
        identifier_label(source.identifier),
        verification.query_url,
        retrieved.isoformat(),
        verification.reason or _field_summary(verification),
        _retraction_summary(verification, retrieved),
        verification.version or "not checked",
        "<br>".join(_claim_summary(claim) for claim in verification.claims)
        or "not checked",
        verification.status.value,
    )
    return "| " + " | ".join(_cell(cell) for cell in cells) + " |"


def _cited_as(source: CitedSource) -> str:
    authors = ", ".join(source.authors) + (
        ", et al." if source.has_more_authors else ""
    )
    details = ", ".join(
        part
        for part in (
            source.volume and f"vol {source.volume}",
            source.pages and f"p {source.pages}",
        )
        if part
    )
    return f"{authors}, {source.title} ({source.year})" + (
        f", {details}" if details else ""
    )


def _field_summary(verification: Verification) -> str:
    parts = [
        check.outcome.value + (f" ({check.detail})" if check.detail else "")
        for check in verification.fields
    ]
    return " / ".join(parts) + (
        f"; venue {verification.venue}" if verification.venue else ""
    )


def _retraction_summary(verification: Verification, retrieved: date) -> str:
    if verification.notices:
        return "; ".join(notice.detail for notice in verification.notices)
    if verification.reason:
        return "not checked"
    return f"none found in {verification.retraction_checked} on {retrieved.isoformat()}"


def _claim_summary(claim: ClaimCheck) -> str:
    where = claim.found_in or "quote not found in the text read"
    return f"{claim.claim} ({where})"


def _cell(text: str) -> str:
    return _WHITESPACE.sub(" ", text).replace("|", "\\|").strip()


# Command line


def _read_input(path: str) -> tuple[str, Path]:
    if path == "-":
        text, base_dir = sys.stdin.read(MAX_INPUT_CHARACTERS + 1), Path.cwd()
    else:
        with Path(path).open(encoding="utf-8") as handle:
            text = handle.read(MAX_INPUT_CHARACTERS + 1)
        base_dir = Path(path).resolve().parent
    if len(text) > MAX_INPUT_CHARACTERS:
        raise ValueError(f"input is over {MAX_INPUT_CHARACTERS} characters")
    return text, base_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check cited references and quoted passages against registries."
    )
    parser.add_argument(
        "sources", help="JSON Lines file of cited sources, or - for standard input"
    )
    args = parser.parse_args(argv)
    # Sources and logs are UTF-8 files; a Windows console defaults to a legacy
    # code page that would garble names on the way in and out.
    for stream in (sys.stdin, sys.stdout):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    try:
        text, base_dir = _read_input(args.sources)
        sources = parse_sources(text, base_dir)
    except (OSError, ValueError) as err:
        print(f"cannot verify {args.sources}: {err}", file=sys.stderr)
        return 2

    client = RegistryClient()
    verifications = [verify(source, client) for source in sources]
    sys.stdout.write(render_log(verifications, date.today()))
    return 0 if all(v.status is Status.VERIFIED for v in verifications) else 1


if __name__ == "__main__":
    sys.exit(main())
