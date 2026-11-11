"""Check cited references and quoted passages against scholarly registries.

Usage:
    verify.py <sources.jsonl>
    verify.py -               read the sources from standard input
    verify.py --refresh <sources.jsonl>
                              ignore cached responses and fetch again
    verify.py --bib <references.bib> <sources.jsonl>
                              also write a BibTeX file of the verified sources
    verify.py --draft <draft.md> <sources.jsonl>
                              also audit the draft's citations and numbers

Each line of the input is one source as the draft cites it:

    {"key": "Feynman1982", "id": "10.1007/BF02650179",
     "title": "Simulating physics with computers", "authors": ["Feynman"],
     "year": 1982, "volume": "21", "pages": "467-488",
     "evidence": [{"claim": "...", "quote": "...", "text": "feynman.html"}]}

`id` is a DOI, looked up in Crossref and then DataCite, or an arXiv
identifier, in any usual form. `authors` lists surnames in order; a final
"et al." stands for the rest, and an empty list cites a work with no
personal authors. `volume` and `pages` are optional. Each quote must appear
word for word in the registry abstract or, when `text` names one, in a saved
copy of the full text: plain text or HTML, inside the input file's folder
(the current folder for standard input).

Prints the verification log as a Markdown table, a row as each source is
checked. Registry responses are kept for 24 hours in `<sources stem>.cache.json`
beside the input file, so a rerun makes no repeat requests; standard input
keeps no cache. Exits 0 if every source is verified, 1 if any is not, 2 if the
input cannot be read or is invalid, and 3 if the run stops on a fault.

`--bib` writes a BibTeX entry for each source whose cited fields all matched
(VERIFIED or CLAIM NOT CHECKED), built from the registry record rather than
the cited fields, so no reference is typed from memory. The file is written
after the checks, also when the run stops on a fault, and a path whose folder
does not exist exits 2 before any request. A write failure exits 3.

`--draft` reads a LaTeX or Markdown draft (UTF-8) and, after the log, prints a
Markdown audit: each cited key that is not in the sources or not VERIFIED,
each number in a cited sentence that no quote from the cited sources holds,
each open gap marker, and each source never cited. An audit error turns exit
0 into 1. A draft that cannot be read exits 2 before any request, and no
audit is printed when the run stops on a fault.
"""

from __future__ import annotations

import argparse
import base64
import bisect
import contextlib
import http.client
import io
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Collection, Sequence
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
MAX_SAVED_TEXT_BYTES = 100 * 1024 * 1024
# Sources not reached in this time are reported unverified, so a run always
# finishes inside a 10-minute command timeout with every row it checked.
MAX_RUN_SECONDS = 300.0
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2.0
MAX_RETRY_WAIT_SECONDS = 30.0
# arXiv asks for one request every three seconds.
ARXIV_INTERVAL_SECONDS = 3.0
EARLIEST_YEAR = 1600
YEAR_DIGITS = 4
USER_AGENT = "writing-skill-verify/0.1"
CACHE_LIFETIME_SECONDS = 24 * 60 * 60
MAX_CACHED_BODY_BYTES = 1_000_000
MAX_CACHE_FILE_BYTES = 64 * 1024 * 1024
CACHE_FORMAT = "writing-verify-cache/1"

CROSSREF_WORKS = "https://api.crossref.org/works/"
DATACITE_DOIS = "https://api.datacite.org/dois/"
OPENALEX_WORKS = "https://api.openalex.org/works/doi:"
OPENALEX_FIELDS = "?select=is_retracted,abstract_inverted_index,open_access"
ARXIV_QUERY = "https://export.arxiv.org/api/query?id_list="
ARXIV_ABS = "https://arxiv.org/abs/"
ARXIV_HOST = "export.arxiv.org"
ARXIV_DOI_PREFIX = "10.48550/arxiv."

_HTTP_NOT_FOUND = 404
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
# Crossref notice types after which the work must not be cited for its content.
_RETRACTING_NOTICES = frozenset({"retraction", "withdrawal", "removal"})
# Crossref work type -> (BibTeX entry type, the field holding the venue). An
# empty field name means the venue is not written.
_CROSSREF_OTHER = ("misc", "howpublished")
_CROSSREF_TYPES = {
    "journal-article": ("article", "journal"),
    "proceedings-article": ("inproceedings", "booktitle"),
    "book-chapter": ("incollection", "booktitle"),
    "book": ("book", ""),
    "monograph": ("book", ""),
    "edited-book": ("book", ""),
}
_CROSSREF_PUBLISHED = frozenset({"incollection", "book"})
# DataCite resourceTypeGeneral, likewise. The venue of a work of any other type
# is its publisher, so it is written as the publisher.
_DATACITE_OTHER = ("misc", "")
_DATACITE_TYPES = {
    "JournalArticle": ("article", "journal"),
    "ConferencePaper": ("inproceedings", "booktitle"),
    "BookChapter": ("incollection", "booktitle"),
    "Book": ("book", ""),
}
_DATACITE_PUBLISHED = frozenset({"incollection", "book", "misc"})
_LATEX_ESCAPES = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
)
# A character LaTeX reads as markup that is not already escaped with a backslash.
_BARE_LATEX_SPECIAL = re.compile(r"(?<!\\)([&%#])")
# What the capital-protection pass leaves alone: maths, commands, backslash
# escapes and text already in braces. Anything else is matched as a word.
_TITLE_WORD_OR_MARKUP = re.compile(
    r"\$\$.*?\$\$|\$.*?\$|\\[A-Za-z]+|\\.|\{[^{}]*\}|(?P<word>\w+)", re.DOTALL
)
# Names of groups of people, which BibTeX splits into given names and a
# surname unless they are braced.
_GROUP_AUTHOR = re.compile(
    r"\b(?:collaboration|consortium|team|group|committee|project|experiment"
    r"|institute|university|laboratory|network|initiative)\b",
    re.IGNORECASE,
)
# Characters BibTeX cannot read in a cite key.
_BIB_KEY_FORBIDDEN = re.compile(r"[\s,{}%#\\]")
# A hyphen or en dash between two page numbers is a range.
_PAGE_RANGE = re.compile(r"(\d)\s*[-\N{EN DASH}]+\s*(\d)")
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
    r"^(?:(?P<new>\d{4}\.\d{4,5})"
    r"|(?P<archive>[a-z-]+)(?:\.[a-z-]+)?/(?P<number>\d{7}))"
    r"(?:v(?P<version>\d+))?$",
    re.IGNORECASE,
)
# arXiv's own wording when a paper is withdrawn, not any comment mentioning one.
_WITHDRAWN = re.compile(r"^\s*withdrawn\b|\b(?:has been|is|was) withdrawn\b", re.I)
_ARXIV_VERSION = re.compile(r"v(\d+)$")
_WHITESPACE = re.compile(r"\s+")
# "p." or "pp." before a page; a bare letter is part of an article number (P04005).
_PAGE_PREFIX = re.compile(r"^\s*pp?(?:\.\s*|\s+)", re.IGNORECASE)
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
    arxiv = _ARXIV.match(_ARXIV_PREFIX.sub("", text).rstrip("/").removesuffix(".pdf"))
    if arxiv:
        version = arxiv["version"]
        return ArxivId(_arxiv_base(arxiv), int(version) if version else None)
    if _DOI.match(doi):
        return Doi(doi)
    raise ValueError(f"expected a DOI or arXiv identifier, got {raw!r}")


def _arxiv_base(match: re.Match[str]) -> str:
    """The identifier as the arXiv API knows it.

    An old-style identifier may carry a subject class (`math.DG/0211159`),
    but the API answers only to the archive and number (`math/0211159`).
    """
    if match["new"]:
        return match["new"]
    return f"{match['archive'].lower()}/{match['number']}"


def identifier_label(identifier: Identifier) -> str:
    if isinstance(identifier, ArxivId):
        return f"arXiv:{identifier}"
    return f"doi:{identifier}"


# Text


class _VisibleText(HTMLParser):
    """The text a reader sees in HTML or JATS markup, without scripts or styles."""

    # Not "head": its end tag is optional, so an unclosed one would hide the page.
    _HIDDEN = frozenset({"script", "style", "noscript", "template"})
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
    decomposed = unicodedata.normalize("NFKD", text)
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
    """Parse JSON Lines of cited sources. Raises ValueError naming the line.

    Saved texts are read relative to `base_dir` and must lie inside it.
    """
    parsed: list[CitedSource] = []
    keys_by_identifier: dict[Identifier, str] = {}
    saved_texts = _SavedTexts(base_dir)
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            source = _parse_source(line, saved_texts)
            _check_unique(source, parsed, keys_by_identifier)
        except ValueError as err:
            raise ValueError(f"line {number}: {err}") from err
        keys_by_identifier[source.identifier] = source.key
        parsed.append(source)
        if len(parsed) > MAX_SOURCES:
            raise ValueError(
                f"more than {MAX_SOURCES} sources; a search this size needs a "
                "systematic review, not a spot check"
            )
    if not parsed:
        raise ValueError("no sources in the input")
    return parsed


def _check_unique(
    source: CitedSource,
    parsed: Sequence[CitedSource],
    keys_by_identifier: dict[Identifier, str],
) -> None:
    if any(earlier.key == source.key for earlier in parsed):
        raise ValueError(f"duplicate key {source.key!r}")
    if source.identifier in keys_by_identifier:
        raise ValueError(
            f"{identifier_label(source.identifier)} is also cited as "
            f"{keys_by_identifier[source.identifier]}"
        )


def _parse_source(line: str, saved_texts: _SavedTexts) -> CitedSource:
    entry = _load_json(line)
    if not isinstance(entry, dict):
        raise ValueError(f"expected an object, got {type(entry).__name__}")
    authors, has_more = _authors(entry.get("authors"))
    return CitedSource(
        key=_bib_key(_required_text(entry, "key")),
        identifier=parse_identifier(_required_text(entry, "id")),
        title=_required_text(entry, "title"),
        authors=authors,
        has_more_authors=has_more,
        year=_year(entry.get("year")),
        volume=_optional_text(entry, "volume"),
        pages=_optional_text(entry, "pages"),
        evidence=_evidence(entry.get("evidence"), saved_texts),
    )


def _bib_key(key: str) -> str:
    forbidden = _BIB_KEY_FORBIDDEN.search(key)
    if forbidden:
        raise ValueError(
            f"key {key!r} contains {forbidden.group()!r}, which BibTeX cannot "
            "read in a cite key"
        )
    return key


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
    # An empty list cites a work with no personal authors, such as an editorial.
    names = [name.strip() for name in value]
    has_more = bool(names) and bool(_ET_AL.match(names[-1]))
    surnames = tuple(names[:-1] if has_more else names)
    if has_more and not surnames:
        raise ValueError("field 'authors' must name an author before 'et al.'")
    return surnames, has_more


def _evidence(value: object, saved_texts: _SavedTexts) -> tuple[Evidence, ...]:
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
        saved = None if text_name is None else saved_texts.read(text_name)
        items.append(Evidence(_required_text(item, "claim"), quote, text_name, saved))
    return tuple(items)


class _SavedTexts:
    """Saved full texts, each read once, inside one folder, within a total size."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder.resolve()
        self._texts: dict[Path, str] = {}
        self._total_bytes = 0

    def read(self, name: str) -> str:
        path = (self._folder / name).resolve()
        if not path.is_relative_to(self._folder):
            raise ValueError(
                f"text file {name} must be inside the folder {self._folder}"
            )
        if path.suffix.lower() == ".pdf":
            raise ValueError(f"text file {name} is a PDF; save the HTML or a text copy")
        if path not in self._texts:
            self._texts[path] = self._load(path, name)
        return self._texts[path]

    def _load(self, path: Path, name: str) -> str:
        try:
            size_bytes = path.stat().st_size
            if size_bytes > MAX_TEXT_FILE_BYTES:
                raise ValueError(
                    f"text file {name} is over {MAX_TEXT_FILE_BYTES} bytes"
                )
            self._total_bytes += size_bytes
            if self._total_bytes > MAX_SAVED_TEXT_BYTES:
                raise ValueError(f"saved texts total over {MAX_SAVED_TEXT_BYTES} bytes")
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            raise ValueError(f"cannot read text file {name}: {err.strerror}") from err
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
            except (OSError, http.client.HTTPException) as err:
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


@dataclass(frozen=True, slots=True)
class _CachedResponse:
    fetched: float
    body: bytes | None


class ResponseCache:
    """A Fetch that keeps the inner fetch's answers for CACHE_LIFETIME_SECONDS.

    Bodies up to MAX_CACHED_BODY_BYTES and 404s are kept. Failures propagate
    and are not recorded. With `refresh`, stored answers are ignored but new
    ones are still stored. A cache file that cannot be used is reported on
    standard error and replaced by `save`. `now` is wall-clock seconds, since
    entries outlive the process.
    """

    def __init__(
        self,
        fetch: Fetch,
        path: Path,
        now: Callable[[], float] = time.time,
        *,
        refresh: bool = False,
    ) -> None:
        self._fetch = fetch
        self._path = path
        self._now = now
        self._refresh = refresh
        self._entries = self._load()

    def __call__(self, url: str) -> bytes | None:
        stored = self._entries.get(url)
        if stored is not None and not self._refresh and self._is_fresh(stored):
            return stored.body
        body = self._fetch(url)
        if body is None or len(body) <= MAX_CACHED_BODY_BYTES:
            self._entries[url] = _CachedResponse(self._now(), body)
        else:
            self._entries.pop(url, None)
        return body

    def save(self) -> None:
        """Write the unexpired entries atomically; a failure is only reported."""
        entries = {
            url: {"fetched": response.fetched, "body": _encode_body(response.body)}
            for url, response in self._entries.items()
            if self._is_fresh(response)
        }
        document = json.dumps({"format": CACHE_FORMAT, "entries": entries})
        temporary = self._path.with_name(self._path.name + ".tmp")
        try:
            temporary.write_text(document, encoding="utf-8")
            os.replace(temporary, self._path)
        except OSError as err:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            print(f"cannot write cache {self._path}: {err}", file=sys.stderr)

    def _is_fresh(self, response: _CachedResponse) -> bool:
        return 0 <= self._now() - response.fetched < CACHE_LIFETIME_SECONDS

    def _load(self) -> dict[str, _CachedResponse]:
        try:
            with self._path.open("rb") as handle:
                raw = handle.read(MAX_CACHE_FILE_BYTES + 1)
            if len(raw) > MAX_CACHE_FILE_BYTES:
                raise ValueError(f"over {MAX_CACHE_FILE_BYTES} bytes")
            return _parse_cache(raw)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as err:
            print(f"ignoring cache {self._path}: {err}", file=sys.stderr)
            return {}


def _encode_body(body: bytes | None) -> str | None:
    return None if body is None else base64.b64encode(body).decode("ascii")


def _parse_cache(raw: bytes) -> dict[str, _CachedResponse]:
    document = _load_json(raw)
    if not isinstance(document, dict) or document.get("format") != CACHE_FORMAT:
        raise ValueError(f"not a {CACHE_FORMAT} file")
    stored = document.get("entries")
    if not isinstance(stored, dict):
        raise ValueError("entries is not an object")
    entries: dict[str, _CachedResponse] = {}
    for url, item in stored.items():
        response = _cached_response(item)
        if response is not None:
            entries[url] = response
    return entries


def _cached_response(item: object) -> _CachedResponse | None:
    """The stored response, or None for a malformed entry."""
    if not isinstance(item, dict):
        return None
    fetched = item.get("fetched")
    if isinstance(fetched, bool) or not isinstance(fetched, int | float):
        return None
    if not math.isfinite(fetched):
        return None
    try:
        body = _decode_body(item.get("body"))
    except (TypeError, ValueError):
        return None
    return _CachedResponse(float(fetched), body)


def _decode_body(encoded: object) -> bytes | None:
    if encoded is None:
        return None
    if not isinstance(encoded, str):
        raise TypeError(f"body is {type(encoded).__name__}, not a string")
    return base64.b64decode(encoded, validate=True)


# Records


@dataclass(frozen=True, slots=True)
class Notice:
    kind: str
    retracts: bool
    detail: str


@dataclass(frozen=True, slots=True)
class BibDetails:
    """What a BibTeX entry needs beyond the fields `Record` already holds.

    `venue_field` names the BibTeX field for the record's venue, or is empty
    when the venue is not written. `title` and `authors` are already LaTeX:
    Crossref and DataCite text is escaped when the record is built, so the
    braces round an organisation survive, while arXiv's is LaTeX as submitted
    and kept. The other text is plain and is escaped when written.
    """

    entry_type: str
    venue_field: str
    title: str
    authors: tuple[str, ...]
    volume: str | None
    issue: str | None
    pages: str | None
    publisher: str | None


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
    open_text: str | None
    bib: BibDetails


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
        return _look_up_datacite(quoted, fetch)
    try:
        work = _as_dict(_load_json(body)).get("message")
    except ValueError as err:
        return Missing(url, f"Crossref returned an unreadable record ({err})")
    if not isinstance(work, dict):
        return Missing(url, "Crossref returned a response without a work record")
    record = _crossref_record(url, work)
    return _with_openalex(record, OPENALEX_WORKS + quoted + OPENALEX_FIELDS, fetch)


def _look_up_datacite(quoted_doi: str, fetch: Fetch) -> Record | Missing:
    """Look up a DOI Crossref does not know. Every reason names both registries."""
    url = DATACITE_DOIS + quoted_doi
    try:
        body = fetch(url)
    except RegistryUnavailableError as err:
        return Missing(url, f"no Crossref record; DataCite unavailable ({err})")
    if body is None:
        return Missing(url, "no Crossref or DataCite record for this DOI")
    unreadable = "no Crossref record; DataCite returned an unreadable record"
    try:
        data = _as_dict(_load_json(body)).get("data")
    except ValueError as err:
        return Missing(url, f"{unreadable} ({err})")
    attributes = _as_dict(data).get("attributes")
    if not isinstance(attributes, dict):
        return Missing(url, f"{unreadable} (no attributes)")
    record = _datacite_record(url, attributes)
    return _with_openalex(record, OPENALEX_WORKS + quoted_doi + OPENALEX_FIELDS, fetch)


def _datacite_record(url: str, attributes: dict[str, Any]) -> Record:
    titles = _datacite_titles(attributes.get("titles"))
    container = _as_dict(attributes.get("container"))
    publisher = attributes.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")
    first_page = _text(container.get("firstPage"))
    return Record(
        query_url=url,
        titles=titles,
        authors=tuple(
            _datacite_surname(creator)
            for creator in _as_list(attributes.get("creators"))
            if isinstance(creator, dict)
        ),
        years=_datacite_years(attributes.get("publicationYear")),
        venue=_text(container.get("title")) or _text(publisher),
        volume=_text(container.get("volume")) or None,
        first_page=first_page or None,
        texts=_datacite_abstract(attributes.get("descriptions")),
        notices=(),
        retraction_checked="DataCite",
        version="version of record",
        open_text=None,
        bib=_datacite_bib(attributes, container, _text(publisher)),
    )


def _datacite_bib(
    attributes: dict[str, Any], container: dict[str, Any], publisher: str
) -> BibDetails:
    resource_type = _as_dict(attributes.get("types")).get("resourceTypeGeneral")
    entry_type, venue_field = _DATACITE_TYPES.get(str(resource_type), _DATACITE_OTHER)
    if venue_field and not _text(container.get("title")):
        # The record's venue would fall back to the publisher, not a journal.
        entry_type, venue_field = _DATACITE_OTHER
    first, last = _text(container.get("firstPage")), _text(container.get("lastPage"))
    title, subtitle = _datacite_title_parts(attributes.get("titles"))
    return BibDetails(
        entry_type=entry_type,
        venue_field=venue_field,
        title=_protect_capitals(_latex_escape(_bib_title(title, subtitle))),
        authors=tuple(
            name
            for creator in _as_list(attributes.get("creators"))
            if (name := _datacite_bib_author(creator))
        ),
        volume=_text(container.get("volume")) or None,
        issue=_text(container.get("issue")) or None,
        pages="--".join(page for page in (first, last) if page) or None,
        publisher=publisher
        if publisher and entry_type in _DATACITE_PUBLISHED
        else None,
    )


def _datacite_bib_author(creator: object) -> str:
    """A creator in BibTeX name form, or "" when it has no name."""
    parts = _as_dict(creator)
    name = _text(parts.get("name"))
    family = _text(parts.get("familyName"))
    if family and parts.get("nameType") != "Organizational":
        return _bib_person(family, _text(parts.get("givenName")))
    # A personal name without its parts is written "Family, Given"; anything
    # else is a group, which BibTeX would otherwise split into given and family.
    if "," in name and parts.get("nameType") != "Organizational":
        return _latex_escape(name)
    return _bib_organisation(name)


def _datacite_titles(value: object) -> tuple[str, ...]:
    title, subtitle = _datacite_title_parts(value)
    return (title, f"{title} {subtitle}") if subtitle else (title,)


def _datacite_title_parts(value: object) -> tuple[str, str]:
    entries = [entry for entry in _as_list(value) if isinstance(entry, dict)]

    def first_of(*kinds: str | None) -> str:
        for entry in entries:
            text = entry.get("title")
            if entry.get("titleType") in kinds and isinstance(text, str) and text:
                return text
        return ""

    return first_of(None), first_of("Subtitle")


def _datacite_surname(creator: dict[str, Any]) -> str:
    family = _text(creator.get("familyName"))
    if family:
        return family
    # A personal name without its parts is written "Family, Given".
    name = _text(creator.get("name"))
    if creator.get("nameType") == "Organizational":
        return name
    return name.split(",")[0].strip()


def _datacite_years(value: object) -> tuple[int, ...]:
    if isinstance(value, int) and not isinstance(value, bool):
        return (value,)
    if isinstance(value, str) and value.strip().isdigit():
        return (int(value),)
    return ()


def _datacite_abstract(value: object) -> tuple[tuple[str, str], ...]:
    for description in _as_list(value):
        if not isinstance(description, dict):
            continue
        text = description.get("description")
        if description.get("descriptionType") == "Abstract" and isinstance(text, str):
            return (("abstract (DataCite)", normalise_passage(visible_text(text))),)
    return ()


def _text(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value.strip() if isinstance(value, str) else ""


def _latex_escape(text: str) -> str:
    return text.translate(_LATEX_ESCAPES)


def _bib_person(family: str, given: str) -> str:
    if not given and _WHITESPACE.search(family):
        # Alone, a family name with spaces would be split into given names.
        return _bib_organisation(family)
    name = _latex_escape(family)
    return f"{name}, {_latex_escape(given)}" if given else name


def _bib_organisation(name: str) -> str:
    """An organisation in braces, so BibTeX does not split it into parts."""
    return f"{{{_latex_escape(name)}}}" if name else ""


def _protect_capitals(text: str) -> str:
    """Brace each word with a capital after its first letter, so a style that
    lowers case keeps acronyms such as LHC.

    Maths, commands, escapes and text already in braces are left as they are.
    """

    def protect(match: re.Match[str]) -> str:
        word = match.group("word")
        if word is not None and any(char.isupper() for char in word[1:]):
            return f"{{{word}}}"
        return match.group()

    return _TITLE_WORD_OR_MARKUP.sub(protect, text)


def _arxiv_bib_title(title: str) -> str:
    """An arXiv title is LaTeX as submitted: only a bare &, % or # is escaped."""
    return _protect_capitals(_BARE_LATEX_SPECIAL.sub(r"\\\1", title))


def _arxiv_bib_author(name: str) -> str:
    escaped = _BARE_LATEX_SPECIAL.sub(r"\\\1", name)
    return f"{{{escaped}}}" if _GROUP_AUTHOR.search(name) else escaped


def _bib_title(title: str, subtitle: str) -> str:
    """The main title, then ": subtitle", as plain text on one line."""
    parts = (
        _WHITESPACE.sub(" ", visible_text(text)).strip() for text in (title, subtitle)
    )
    return ": ".join(part for part in parts if part)


def _crossref_bib(work: dict[str, Any]) -> BibDetails:
    entry_type, venue_field = _CROSSREF_TYPES.get(
        str(work.get("type")), _CROSSREF_OTHER
    )
    publisher = _text(work.get("publisher"))
    return BibDetails(
        entry_type=entry_type,
        venue_field=venue_field,
        title=_protect_capitals(
            _latex_escape(
                _bib_title(_first(work.get("title")), _first(work.get("subtitle")))
            )
        ),
        authors=tuple(
            name
            for author in _as_list(work.get("author"))
            if (name := _crossref_bib_author(author))
        ),
        volume=_text(work.get("volume")) or None,
        issue=_text(work.get("issue")) or None,
        pages=_PAGE_RANGE.sub(r"\1--\2", _text(work.get("page")))
        or _text(work.get("article-number"))
        or None,
        publisher=publisher
        if publisher and entry_type in _CROSSREF_PUBLISHED
        else None,
    )


def _crossref_bib_author(author: object) -> str:
    """An author in BibTeX name form, or "" when it has no name."""
    parts = _as_dict(author)
    family = _text(parts.get("family"))
    if family:
        return _bib_person(family, _text(parts.get("given")))
    return _bib_organisation(_text(parts.get("name")))


def _crossref_record(url: str, work: dict[str, Any]) -> Record:
    title = _first(work.get("title"))
    subtitle = _first(work.get("subtitle"))
    titles = (title, f"{title} {subtitle}") if subtitle else (title,)
    authors = tuple(
        str(author.get("family") or author.get("name") or "")
        for author in _as_list(work.get("author"))
        if isinstance(author, dict)
    )
    years = tuple(
        dict.fromkeys(
            year
            for name in ("issued", "published-print", "published-online")
            if (year := _date_year(work.get(name))) is not None
        )
    )
    page = work.get("page")
    first_page = str(page).split("-")[0] if page else work.get("article-number")
    abstract = work.get("abstract")
    texts = (
        (("abstract (Crossref)", normalise_passage(visible_text(abstract))),)
        if isinstance(abstract, str) and abstract
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
        notices=_crossref_notices(_as_list(work.get("updated-by"))),
        retraction_checked="Crossref",
        version="version of record",
        open_text=None,
        bib=_crossref_bib(work),
    )


def _crossref_notices(updates: list[Any]) -> tuple[Notice, ...]:
    notices: dict[tuple[str, str], Notice] = {}
    for update in updates:
        if not isinstance(update, dict):
            continue
        kind = str(update.get("type", "update"))
        notice_doi = str(update.get("DOI", ""))
        when = "-".join(f"{part:02d}" for part in _date_parts(update.get("updated")))
        label = update.get("label") or kind
        notices.setdefault(
            (kind, notice_doi),
            Notice(
                kind, kind in _RETRACTING_NOTICES, f"{label} doi:{notice_doi} ({when})"
            ),
        )
    return tuple(notices.values())


def _with_openalex(record: Record, url: str, fetch: Fetch) -> Record:
    registry = record.retraction_checked
    try:
        body = fetch(url)
        work = _load_json(body) if body is not None else None
    except RegistryUnavailableError as err:
        return replace(
            record, retraction_checked=f"{registry}; OpenAlex unavailable ({err})"
        )
    except ValueError:
        return replace(
            record, retraction_checked=f"{registry}; OpenAlex record unreadable"
        )
    if not isinstance(work, dict):
        return replace(record, retraction_checked=f"{registry}; no OpenAlex record")
    notices = record.notices
    if work.get("is_retracted") is True:
        notices += (Notice("retracted", True, "OpenAlex marks it retracted"),)
    texts = record.texts
    abstract = _from_inverted_index(work.get("abstract_inverted_index"))
    if abstract:
        texts += (("abstract (OpenAlex)", normalise_passage(abstract)),)
    return replace(
        record,
        notices=notices,
        texts=texts,
        retraction_checked=f"{registry} and OpenAlex",
        open_text=_open_access_url(work.get("open_access")),
    )


def _open_access_url(value: object) -> str | None:
    """OpenAlex's free full-text URL, if it is a web address."""
    url = _as_dict(value).get("oa_url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return url
    return None


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


def _load_json(text: str | bytes) -> object:
    """Parse JSON, raising ValueError for anything unreadable, however deep."""
    try:
        return json.loads(text)
    except RecursionError as err:
        raise ValueError("JSON nested too deeply") from err


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _date_parts(value: object) -> list[int]:
    """The leading numeric parts (year, month, day) of a Crossref date."""
    parts = _as_list(_as_dict(value).get("date-parts"))
    numbers: list[int] = []
    for part in _as_list(parts[0]) if parts else []:
        if not isinstance(part, int) or isinstance(part, bool):
            break
        numbers.append(part)
    return numbers


def _date_year(value: object) -> int | None:
    parts = _date_parts(value)
    return parts[0] if parts else None


def _first(value: object) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value) if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class _ArxivEntry:
    version: int
    title: str
    authors: tuple[str, ...]
    published_year: int | None
    updated_year: int | None
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
    return _arxiv_record(url, arxiv.base, cited, latest)


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
        published_year=_leading_year(text(f"{_ATOM}published")),
        updated_year=_leading_year(text(f"{_ATOM}updated")),
        summary=text(f"{_ATOM}summary"),
        comment=text(f"{_ARXIV_NS}comment"),
        journal_ref=text(f"{_ARXIV_NS}journal_ref"),
        doi=text(f"{_ARXIV_NS}doi"),
    )


def _leading_year(timestamp: str) -> int | None:
    year = timestamp[:YEAR_DIGITS]
    return int(year) if len(year) == YEAR_DIGITS and year.isdigit() else None


def _arxiv_record(
    url: str, base: str, cited: _ArxivEntry, latest: _ArxivEntry
) -> Record:
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
    if _WITHDRAWN.search(latest.comment):
        notices = (
            Notice("withdrawn", True, f"arXiv v{latest.version}: {latest.comment}"),
        )
    return Record(
        query_url=url,
        titles=(cited.title,),
        authors=cited.authors,
        years=tuple(
            dict.fromkeys(
                year
                for year in (cited.published_year, cited.updated_year)
                if year is not None
            )
        ),
        venue="arXiv",
        volume=None,
        first_page=None,
        texts=(
            (f"abstract (arXiv v{cited.version})", normalise_passage(cited.summary)),
        ),
        notices=notices,
        retraction_checked="arXiv comments",
        version=version,
        open_text=f"{ARXIV_ABS}{base}v{cited.version}",
        bib=BibDetails(
            entry_type="misc",
            venue_field="",
            title=_arxiv_bib_title(cited.title),
            authors=tuple(_arxiv_bib_author(name) for name in cited.authors if name),
            volume=None,
            issue=None,
            pages=None,
            publisher=None,
        ),
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
    open_text: str | None
    bib: BibDetails | None


def verify(source: CitedSource, fetch: Fetch) -> Verification:
    lookup = look_up(source.identifier, fetch)
    if isinstance(lookup, Missing):
        return unchecked(source, lookup.query_url, lookup.reason)
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
        lookup.open_text,
        lookup.bib,
    )


def unchecked(source: CitedSource, query_url: str, reason: str) -> Verification:
    """A source no record was compared with, and why."""
    return Verification(
        source,
        Status.UNVERIFIED,
        query_url,
        reason,
        "",
        "",
        (),
        (),
        (),
        "not checked",
        None,
        None,
    )


def compare_fields(source: CitedSource, record: Record) -> tuple[FieldCheck, ...]:
    return (
        _check_title(source.title, record.titles),
        _check_authors(source, record.authors),
        _check_year(source.year, record.years),
        _check_optional("volume", source.volume, record.volume),
        _check_optional(
            "first page",
            _first_page(source.pages) if source.pages else None,
            record.first_page,
        ),
    )


def _first_page(pages: str) -> str:
    """The first page of a range as cited: `pp. 467-488` gives `467`."""
    return normalise_passage(_PAGE_PREFIX.sub("", pages)).split("-")[0].strip()


def _check_title(cited: str, titles: tuple[str, ...]) -> FieldCheck:
    # Registry titles carry markup and entities; the cited title is plain text.
    wanted = _comparable(cited)
    recorded = (_RETRACTED_TITLE_PREFIX.sub("", visible_text(t)) for t in titles)
    if any(_comparable(title) == wanted for title in recorded):
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


# The log is printed a row at a time, so a run cut short keeps what it checked.
LOG_HEADER = "| " + " | ".join(_COLUMNS) + " |\n|" + "---|" * len(_COLUMNS)


def log_summary(verifications: Sequence[Verification]) -> str:
    verified = sum(v.status is Status.VERIFIED for v in verifications)
    return f"{verified} of {len(verifications)} sources verified."


def log_row(verification: Verification, retrieved: date) -> str:
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
        "<br>".join(
            _claim_summary(claim, verification.open_text)
            for claim in verification.claims
        )
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
    byline = f"{authors}, " if authors else ""
    return f"{byline}{source.title} ({source.year})" + (
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


def _claim_summary(claim: ClaimCheck, open_text: str | None) -> str:
    if claim.found_in is not None:
        return f"{claim.claim} ({claim.found_in})"
    hint = f"; full text may be at {open_text}" if open_text else ""
    return f"{claim.claim} (quote not found in the text read{hint})"


def _cell(text: str) -> str:
    return _WHITESPACE.sub(" ", text).replace("|", "\\|").strip()


# BibTeX


# The statuses whose cited fields all matched the record.
_BIB_STATUSES = frozenset({Status.VERIFIED, Status.CLAIM_NOT_CHECKED})


def _is_bib_ready(verification: Verification) -> bool:
    return verification.bib is not None and verification.status in _BIB_STATUSES


def bib_entry(verification: Verification) -> str | None:
    """The BibTeX entry for a source, or None when its fields did not all match.

    The entry comes from the registry record, not from the cited fields.
    """
    details = verification.bib
    if details is None or not _is_bib_ready(verification):
        return None
    lines = [
        f"  {name} = {{{value}}},"
        for name, value in _bib_fields(verification, details)
        if value
    ]
    key = verification.source.key
    return "\n".join([f"@{details.entry_type}{{{key},", *lines, "}"])


def _bib_fields(
    verification: Verification, details: BibDetails
) -> list[tuple[str, str]]:
    source = verification.source
    identifier = source.identifier
    # Identifiers are read by URL macros, so they are not escaped.
    identifiers = (
        [("eprint", str(identifier)), ("archivePrefix", "arXiv")]
        if isinstance(identifier, ArxivId)
        else [("doi", identifier)]
    )
    venue = _latex_escape(verification.venue) if details.venue_field else ""
    return [
        ("author", " and ".join(details.authors)),
        ("title", details.title),
        (details.venue_field, venue),
        ("publisher", _latex_escape(details.publisher or "")),
        ("volume", _latex_escape(details.volume or "")),
        ("number", _latex_escape(details.issue or "")),
        ("pages", _latex_escape(details.pages or "")),
        ("year", str(source.year)),
        *identifiers,
    ]


def render_bib(verifications: Sequence[Verification]) -> str:
    """The entries of every source that may be cited, in the sources' order."""
    entries = [entry for v in verifications if (entry := bib_entry(v)) is not None]
    return "\n\n".join(entries) + "\n" if entries else ""


def bib_report(
    sources: Sequence[CitedSource],
    verifications: Sequence[Verification],
    path: Path,
) -> str:
    """One line: how many sources were written, and which were left out and why."""
    ready = {v.source.key for v in verifications if _is_bib_ready(v)}
    statuses = {v.source.key: v.status.value for v in verifications}
    left_out = [
        f"{source.key} ({statuses.get(source.key, 'NOT CHECKED')})"
        for source in sources
        if source.key not in ready
    ]
    line = f"wrote {len(ready)} of {len(sources)} sources to {path}"
    return f"{line}; left out: {', '.join(left_out)}" if left_out else line


# Draft audit


MAX_UNCHECKED_INTEGER = 10
# `\nocite{*}` cites every source in the bibliography.
ALL_SOURCES_KEY = "*"
NO_CITES_NOTICE = (
    r"no LaTeX \cite or Pandoc [@key] citations found, "
    "so keys and numbers were not checked"
)

_LATEX_CITE = re.compile(
    r"\\[A-Za-z]*[Cc]ite[A-Za-z]*\*?(?:\s*\[[^\[\]]*\]){0,2}\s*\{([^{}]*)\}"
)
# An escaped character (`\%` included) is kept; an unescaped `%` runs to the line end.
_LATEX_COMMENT = re.compile(r"\\.|%[^\n]*")
_PANDOC_BRACKET = re.compile(r"\[([^\[\]]*)\]")
_PANDOC_KEY_BODY = r"@(\w(?:\w|[:.#$%&+?<>~/-](?=\w))*)"
_PANDOC_KEY = re.compile(r"(?<!\w)-?" + _PANDOC_KEY_BODY)
# Outside brackets Pandoc reads `@key` only after a line start, a space or an
# opening bracket, so `me@host` and `x.@y` are not citations.
_PANDOC_BARE_KEY = re.compile(r"(?:^|(?<=[\s(\[{]))-?" + _PANDOC_KEY_BODY, re.MULTILINE)
# Kept equal to check.py's GAP_MARKER: the scripts cannot import each other.
GAP_MARKER = (
    r"\[(?:UNVERIFIED|CITATION NEEDED|CLAIM NOT CHECKED|DATA NEEDED)(?::[^\]]*)?\]"
)
_MARKER = re.compile(GAP_MARKER, re.IGNORECASE)
# A sentence ends at terminal punctuation before a capital or backslash, at a
# blank line, and around a Markdown heading line, which belongs to no sentence.
_SENTENCE_BREAK = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z\\])|\n[ \t]*\n\s*|^#{1,6}[ \t].*$", re.MULTILINE
)
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    MARKER = "marker"


@dataclass(frozen=True, slots=True)
class AuditFinding:
    line: int
    severity: Severity
    text: str


@dataclass(frozen=True, slots=True)
class DraftAudit:
    has_cites: bool
    findings: tuple[AuditFinding, ...]
    uncited: tuple[str, ...]

    @property
    def has_errors(self) -> bool:
        return any(f.severity is Severity.ERROR for f in self.findings)


@dataclass(frozen=True, slots=True)
class _Span:
    """A stretch of the draft that is not prose: a cite or a gap marker."""

    start: int
    end: int
    keys: tuple[str, ...]


class _Lines:
    def __init__(self, text: str) -> None:
        self._breaks = [match.start() for match in re.finditer("\n", text)]

    def number(self, offset: int) -> int:
        return bisect.bisect_left(self._breaks, offset) + 1


def audit_draft(
    text: str,
    sources: Sequence[CitedSource],
    verifications: Sequence[Verification],
    *,
    latex: bool = False,
) -> DraftAudit:
    """Check a draft's cites, numbers and gap markers against the verified sources.

    A LaTeX draft has its `%` comments dropped first, so a commented-out cite
    is not audited. Line numbers are unchanged.
    """
    if latex:
        text = _LATEX_COMMENT.sub(_keep_escape, text)
    lines = _Lines(text)
    by_key = {source.key: source for source in sources}
    cites = _cite_spans(text, by_key.keys())
    markers = list(_MARKER.finditer(text))
    spans = sorted(
        [*cites, *(_Span(m.start(), m.end(), ()) for m in markers)],
        key=lambda span: span.start,
    )
    findings: list[AuditFinding] = []
    uncited: tuple[str, ...] = ()
    if cites:
        statuses = {v.source.key: v.status for v in verifications}
        findings += _cite_findings(cites, lines, by_key, statuses)
        findings += _number_findings(text, spans, by_key, lines)
        cited = {key for span in cites for key in span.keys}
        if ALL_SOURCES_KEY not in cited:
            uncited = tuple(key for key in by_key if key not in cited)
    findings += (
        AuditFinding(lines.number(m.start()), Severity.MARKER, _squash(m.group()))
        for m in markers
    )
    ordered = sorted(dict.fromkeys(findings), key=lambda finding: finding.line)
    return DraftAudit(bool(cites), tuple(ordered), uncited)


def _keep_escape(match: re.Match[str]) -> str:
    return match.group() if match.group().startswith("\\") else ""


def _squash(text: str) -> str:
    return _WHITESPACE.sub(" ", text)


def _cite_spans(text: str, source_keys: Collection[str]) -> list[_Span]:
    spans = [
        _Span(match.start(), match.end(), _split_keys(match.group(1)))
        for match in _LATEX_CITE.finditer(text)
    ]
    for bracket in _PANDOC_BRACKET.finditer(text):
        keys = tuple(_PANDOC_KEY.findall(bracket.group(1)))
        spans.append(_Span(bracket.start(), bracket.end(), keys))
    spans += _bare_pandoc_spans(text, source_keys, spans)
    return sorted((span for span in spans if span.keys), key=lambda span: span.start)


def _bare_pandoc_spans(
    text: str, source_keys: Collection[str], taken: Sequence[_Span]
) -> list[_Span]:
    """Pandoc `@key` cites outside brackets.

    Only a key in the sources counts, so a mention is not read as a citation.
    """
    return [
        _Span(match.start(), match.end(), (match.group(1),))
        for match in _PANDOC_BARE_KEY.finditer(text)
        if match.group(1) in source_keys
        and not any(span.start <= match.start() < span.end for span in taken)
    ]


def _split_keys(keys: str) -> tuple[str, ...]:
    return tuple(key for part in keys.split(",") if (key := part.strip()))


def _cite_findings(
    cites: Sequence[_Span],
    lines: _Lines,
    by_key: dict[str, CitedSource],
    statuses: dict[str, Status],
) -> list[AuditFinding]:
    found = (
        _key_finding(lines.number(span.start), key, by_key, statuses)
        for span in cites
        for key in span.keys
    )
    return [finding for finding in found if finding is not None]


def _key_finding(
    line: int,
    key: str,
    by_key: dict[str, CitedSource],
    statuses: dict[str, Status],
) -> AuditFinding | None:
    if key == ALL_SOURCES_KEY:
        return None
    if key not in by_key:
        return AuditFinding(
            line, Severity.ERROR, f"`{key}` is cited but not in the sources"
        )
    status = statuses.get(key)
    if status is None or status is Status.VERIFIED:
        return None
    severity = (
        Severity.WARNING if status is Status.CLAIM_NOT_CHECKED else Severity.ERROR
    )
    return AuditFinding(line, severity, f"`{key}` is cited but {status.value}")


def _numbers(text: str) -> list[str]:
    return _NUMBER.findall(_THOUSANDS_COMMA.sub("", text))


def _number_findings(
    text: str,
    spans: Sequence[_Span],
    by_key: dict[str, CitedSource],
    lines: _Lines,
) -> list[AuditFinding]:
    quoted = {
        key: {n for evidence in source.evidence for n in _numbers(evidence.quote)}
        for key, source in by_key.items()
    }
    starts = [span.start for span in spans]
    findings: list[AuditFinding] = []
    for begin, end in _sentence_bounds(_mask(text, spans)):
        first = bisect.bisect_left(starts, begin)
        inside = spans[first : bisect.bisect_left(starts, end)]
        keys = list(dict.fromkeys(k for s in inside for k in s.keys if k in by_key))
        if not keys:
            continue
        supported = set().union(*(quoted[key] for key in keys))
        years = {str(by_key[key].year) for key in keys}
        names = ", ".join(f"`{key}`" for key in keys)
        line = lines.number(begin)
        findings += (
            AuditFinding(
                line, Severity.WARNING, f"{n} appears in no quote from {names}"
            )
            for n in _numbers(_prose(text, begin, end, inside))
            if _needs_quote(n, years) and n not in supported
        )
    return findings


def _needs_quote(number: str, years: set[str]) -> bool:
    # float, not int: a string of thousands of digits overflows to inf
    # rather than raising.
    if number in years:
        return False
    return "." in number or float(number) > MAX_UNCHECKED_INTEGER


def _mask(text: str, spans: Sequence[_Span]) -> str:
    """The text with each span's body replaced by underscores, length kept.

    The first character stays, so a cite that opens a sentence still starts one.
    """
    pieces: list[str] = []
    position = 0
    for span in spans:
        if span.end <= position:
            continue
        begin = max(span.start, position)
        pieces += [text[position:begin], text[begin], "_" * (span.end - begin - 1)]
        position = span.end
    pieces.append(text[position:])
    return "".join(pieces)


def _sentence_bounds(masked: str) -> list[tuple[int, int]]:
    bounds: list[tuple[int, int]] = []
    begin = 0
    for gap in [*_SENTENCE_BREAK.finditer(masked), None]:
        end = len(masked) if gap is None else gap.start()
        sentence = masked[begin:end]
        bounds.append((begin + len(sentence) - len(sentence.lstrip()), end))
        begin = end if gap is None else gap.end()
    return bounds


def _prose(text: str, begin: int, end: int, spans: Sequence[_Span]) -> str:
    pieces: list[str] = []
    position = begin
    for span in spans:
        if span.end <= position:
            continue
        pieces.append(text[position : max(span.start, position)])
        position = span.end
    pieces.append(text[position:end])
    return " ".join(pieces)


def render_audit(audit: DraftAudit) -> str:
    """The audit as Markdown: a bullet per finding, then a count line."""
    bullets = [_bullet(finding) for finding in audit.findings]
    bullets += (f"- `{key}` is in the sources but never cited" for key in audit.uncited)
    notice = "" if audit.has_cites else f"{NO_CITES_NOTICE}\n\n"
    body = "\n".join(bullets) if bullets else "Nothing to report."
    return f"\n## Draft audit\n\n{notice}{body}\n\n{_audit_counts(audit)}"


def _bullet(finding: AuditFinding) -> str:
    if finding.severity is Severity.MARKER:
        return f"- line {finding.line}: open marker {finding.text}"
    return f"- line {finding.line}: {finding.severity.value}: {finding.text}"


def _audit_counts(audit: DraftAudit) -> str:
    def count(severity: Severity) -> int:
        return sum(1 for finding in audit.findings if finding.severity is severity)

    parts = [
        _counted(count(Severity.ERROR), "error"),
        _counted(count(Severity.WARNING), "warning"),
        _counted(count(Severity.MARKER), "open marker"),
        _counted(len(audit.uncited), "uncited source"),
    ]
    return f"Draft audit: {', '.join(parts)}."


def _counted(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


# Command line


def _bib_path_problem(path: Path) -> str | None:
    if path.is_dir():
        return "it is a directory"
    if not path.parent.is_dir():
        return f"the folder {path.parent} does not exist"
    return None


def _write_bib(
    sources: Sequence[CitedSource],
    verifications: Sequence[Verification],
    path: Path,
) -> bool:
    """Write the BibTeX file and report it. False when it could not be written."""
    try:
        path.write_text(render_bib(verifications), encoding="utf-8", newline="\n")
    except OSError as err:
        print(f"cannot write {path}: {err}", file=sys.stderr)
        return False
    print(bib_report(sources, verifications, path), file=sys.stderr)
    return True


def _read_input(path: str) -> tuple[str, Path]:
    if path == "-":
        text, base_dir = sys.stdin.read(MAX_INPUT_CHARACTERS + 1), Path.cwd()
    else:
        with Path(path).open(encoding="utf-8") as handle:
            text = handle.read(MAX_INPUT_CHARACTERS + 1)
        base_dir = Path(path).resolve().parent
    _require_within_limit(text)
    return text, base_dir


def _require_within_limit(text: str) -> None:
    if len(text) > MAX_INPUT_CHARACTERS:
        raise ValueError(f"input is over {MAX_INPUT_CHARACTERS} characters")


def _read_draft(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        text = handle.read(MAX_INPUT_CHARACTERS + 1)
    _require_within_limit(text)
    return text


def _cache_path(sources: str) -> Path:
    path = Path(sources).resolve()
    return path.with_name(f"{path.stem}.cache.json")


def _check_all(
    sources: Sequence[CitedSource], fetch: Fetch, verifications: list[Verification]
) -> int:
    """Check each source, adding each verification to `verifications` as made."""
    retrieved = date.today()
    print(LOG_HEADER, flush=True)
    deadline = time.monotonic() + MAX_RUN_SECONDS
    for source in sources:
        try:
            if time.monotonic() > deadline:
                verification = unchecked(
                    source,
                    "",
                    f"run time limit of {MAX_RUN_SECONDS:.0f} s reached; rerun",
                )
            else:
                verification = verify(source, fetch)
        except Exception as err:
            # The process boundary: an unforeseen fault is reported once, and
            # the rows already printed stay valid.
            print(f"verify.py stopped at {source.key}: {err!r}", file=sys.stderr)
            return 3
        verifications.append(verification)
        print(log_row(verification, retrieved), flush=True)
    print(f"\n{log_summary(verifications)}")
    return 0 if all(v.status is Status.VERIFIED for v in verifications) else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check cited references and quoted passages against registries."
    )
    parser.add_argument(
        "sources", help="JSON Lines file of cited sources, or - for standard input"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="ignore cached responses and fetch again",
    )
    parser.add_argument(
        "--bib",
        type=Path,
        metavar="PATH",
        help="write a BibTeX file of the sources whose cited fields all matched",
    )
    parser.add_argument(
        "--draft",
        type=Path,
        metavar="PATH",
        help="audit the citations, numbers and gap markers of a draft",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    problem = None if args.bib is None else _bib_path_problem(args.bib)
    if problem is not None:
        print(f"cannot write {args.bib}: {problem}", file=sys.stderr)
        return 2
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
    try:
        draft = None if args.draft is None else _read_draft(args.draft)
    except (OSError, ValueError) as err:
        print(f"cannot audit {args.draft}: {err}", file=sys.stderr)
        return 2

    verifications: list[Verification] = []
    code = _run_checks(sources, args, verifications)
    is_latex = args.draft is not None and args.draft.suffix.lower() == ".tex"
    code = _audited_code(draft, is_latex, sources, verifications, code)
    if args.bib is not None and not _write_bib(sources, verifications, args.bib):
        return 3
    return code


def _audited_code(
    draft: str | None,
    is_latex: bool,
    sources: Sequence[CitedSource],
    verifications: Sequence[Verification],
    code: int,
) -> int:
    """Print the draft audit, and return the exit code it leaves."""
    if draft is None or code not in (0, 1):
        return code
    audit = audit_draft(draft, sources, verifications, latex=is_latex)
    print(render_audit(audit))
    return 1 if audit.has_errors else code


def _run_checks(
    sources: Sequence[CitedSource],
    args: argparse.Namespace,
    verifications: list[Verification],
) -> int:
    client = RegistryClient()
    if args.sources == "-":
        return _check_all(sources, client, verifications)
    cache = ResponseCache(client, _cache_path(args.sources), refresh=args.refresh)
    try:
        return _check_all(sources, cache, verifications)
    finally:
        cache.save()


if __name__ == "__main__":
    sys.exit(main())
