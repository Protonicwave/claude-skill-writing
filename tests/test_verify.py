import base64
import email.message
import http.client
import io
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

import pytest
import verify as verify_module
from verify import (
    CACHE_FORMAT,
    CACHE_LIFETIME_SECONDS,
    LOG_HEADER,
    MAX_CACHED_BODY_BYTES,
    ArxivId,
    CitedSource,
    Fetch,
    Outcome,
    RegistryClient,
    RegistryUnavailableError,
    ResponseCache,
    Status,
    Verification,
    log_row,
    log_summary,
    main,
    parse_identifier,
    parse_sources,
    verify,
)

FEYNMAN_ABSTRACT = (
    "<jats:p>The question is, if we wrote a Hamiltonian which involved only "
    "these operators, locally coupled to corresponding operators on the "
    "other space-time points, could we imitate every quantum mechanical "
    "system?</jats:p>"
)
FEYNMAN_QUOTE = "could we imitate every quantum mechanical system?"
ATTENTION_V1 = (
    "On the WMT 2014 English-to-French translation task, our model "
    "establishes a new single-model state-of-the-art BLEU score of 41.0 "
    "after training for 3.5 days on eight GPUs."
)
ATTENTION_V7 = ATTENTION_V1.replace("41.0", "41.8")
VASWANI_AUTHORS = ("Ashish Vaswani", "Noam Shazeer", "Niki Parmar")


def families(*names: str) -> list[dict[str, str]]:
    return [{"family": name, "given": "A."} for name in names]


def notices(*entries: tuple[str, str]) -> dict[str, object]:
    updates = [
        {
            "type": kind,
            "label": kind.capitalize(),
            "DOI": notice_doi,
            "updated": {"date-parts": [[2023, 11, 7]]},
        }
        for kind, notice_doi in entries
    ]
    return {"updated-by": updates}


def crossref(**changes: object) -> bytes:
    """A Crossref works response for Feynman 1982, with fields replaced.

    A field set to None is left out of the record.
    """
    work: dict[str, object] = {
        "title": ["Simulating physics with computers"],
        "author": families("Feynman"),
        "issued": {"date-parts": [[1982, 6]]},
        "container-title": ["International Journal of Theoretical Physics"],
        "volume": "21",
        "page": "467-488",
        "abstract": FEYNMAN_ABSTRACT,
    }
    work.update(changes)
    present = {name: value for name, value in work.items() if value is not None}
    return json.dumps({"status": "ok", "message": present}).encode()


def datacite(**changes: object) -> bytes:
    """A DataCite DOI response for Feynman 1982, with attributes replaced.

    An attribute set to None is left out of the record.
    """
    attributes: dict[str, object] = {
        "titles": [{"title": "Simulating physics with computers"}],
        "creators": [
            {"name": "Feynman, R.", "familyName": "Feynman", "givenName": "R."}
        ],
        "publicationYear": 1982,
        "container": {
            "title": "International Journal of Theoretical Physics",
            "volume": "21",
            "firstPage": "467",
        },
        "publisher": "Springer",
        "descriptions": [
            {"description": FEYNMAN_QUOTE.capitalize(), "descriptionType": "Other"},
            {
                "description": "We ask: " + FEYNMAN_QUOTE,
                "descriptionType": "Abstract",
            },
        ],
        "types": {"resourceTypeGeneral": "JournalArticle"},
    }
    attributes.update(changes)
    present = {name: value for name, value in attributes.items() if value is not None}
    return json.dumps({"data": {"attributes": present}}).encode()


def openalex(
    *,
    retracted: bool = False,
    abstract: str | None = None,
    oa_url: object = None,
) -> bytes:
    """An OpenAlex work. An `oa_url` of None leaves out `open_access`."""
    index: dict[str, list[int]] = {}
    for position, word in enumerate((abstract or "").split()):
        index.setdefault(word, []).append(position)
    work: dict[str, object] = {
        "is_retracted": retracted,
        "abstract_inverted_index": index or None,
    }
    if oa_url is not None:
        work["open_access"] = {"oa_url": oa_url}
    return json.dumps(work).encode()


def atom(
    *,
    version: int,
    summary: str,
    extras: str = "<arxiv:comment>15 pages</arxiv:comment>",
    authors: Sequence[str] = VASWANI_AUTHORS,
) -> bytes:
    """An arXiv API feed holding one version of "Attention Is All You Need"."""
    names = "".join(f"<author><name>{name}</name></author>" for name in authors)
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v{version}</id>
    <title>Attention Is All
      You Need</title>
    <updated>2017-08-02T00:41:18Z</updated>
    <published>2017-06-12T17:57:34Z</published>
    <summary>{summary}</summary>
    {extras}
    {names}
  </entry>
</feed>""".encode()


EMPTY_ATOM = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>0</opensearch:totalResults>
</feed>"""


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


def entry(**fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "key": "Feynman1982",
        "id": "10.1007/BF02650179",
        "title": "Simulating Physics with Computers",
        "authors": ["Feynman"],
        "year": 1982,
        "volume": "21",
        "pages": "467-488",
        "evidence": [
            {
                "claim": "Quantum systems need quantum simulators.",
                "quote": FEYNMAN_QUOTE,
            }
        ],
    }
    base.update(fields)
    return base


def sources(*entries: dict[str, object], base_dir: Path = Path()) -> list[CitedSource]:
    return parse_sources("\n".join(json.dumps(e) for e in entries), base_dir)


def check(fields: dict[str, object], fetch: Fetch) -> Verification:
    (source,) = sources(entry(**fields))
    return verify(source, fetch)


def doi_registry(
    work: bytes | None = None, alex: bytes | Exception | None = None
) -> FakeRegistry:
    return FakeRegistry(
        [
            ("api.crossref.org", crossref() if work is None else work),
            ("api.openalex.org", openalex() if alex is None else alex),
        ]
    )


def datacite_registry(
    record: bytes | Exception | None, alex: bytes | Exception | None = None
) -> FakeRegistry:
    """A registry where Crossref has no record and DataCite answers `record`."""
    return FakeRegistry(
        [
            ("api.crossref.org", None),
            ("api.datacite.org", record),
            ("api.openalex.org", openalex() if alex is None else alex),
        ]
    )


def outcomes(verification: Verification) -> dict[str, Outcome]:
    return {check.field: check.outcome for check in verification.fields}


# Identifiers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1007/BF02650179", "10.1007/bf02650179"),
        ("doi:10.1007/BF02650179", "10.1007/bf02650179"),
        ("https://doi.org/10.1007/BF02650179", "10.1007/bf02650179"),
        ("http://dx.doi.org/10.1007/BF02650179", "10.1007/bf02650179"),
        ("1706.03762", ArxivId("1706.03762", None)),
        ("arXiv:1706.03762v5", ArxivId("1706.03762", 5)),
        ("https://arxiv.org/abs/1706.03762v1", ArxivId("1706.03762", 1)),
        ("https://arxiv.org/pdf/1706.03762", ArxivId("1706.03762", None)),
        ("hep-th/9711200", ArxivId("hep-th/9711200", None)),
        ("math.GT/0309136", ArxivId("math/0309136", None)),
        ("arXiv:math.gt/0309136v2", ArxivId("math/0309136", 2)),
        ("https://arxiv.org/abs/1706.03762/", ArxivId("1706.03762", None)),
        ("10.48550/arXiv.1706.03762", ArxivId("1706.03762", None)),
    ],
)
def test_parse_identifier_accepts_usual_forms(raw: str, expected: object) -> None:
    assert parse_identifier(raw) == expected


@pytest.mark.parametrize("raw", ["", "Feynman 1982", "10.1007", "arXiv:17.0376"])
def test_parse_identifier_rejects_other_text(raw: str) -> None:
    with pytest.raises(ValueError, match="DOI or arXiv"):
        parse_identifier(raw)


# Input


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "no sources"),
        ("\n\n", "no sources"),
        ("{not json", "line 1"),
        ("[1, 2]", "line 1: expected an object"),
        (json.dumps(entry(title="")), "line 1: field 'title'"),
        (json.dumps({k: v for k, v in entry().items() if k != "year"}), "'year'"),
        (json.dumps(entry(year="1982")), "'year'"),
        (json.dumps(entry(year=True)), "'year'"),
        (json.dumps(entry(year=1599)), "'year'"),
        (json.dumps(entry(year=3000)), "'year'"),
        (
            json.dumps(entry(evidence=[{"claim": "x", "quote": FEYNMAN_QUOTE}] * 21)),
            "1 to 20",
        ),
        (json.dumps(entry(authors="Feynman")), "'authors'"),
        (json.dumps(entry(authors=["et al."])), "'authors'"),
        (json.dumps(entry(evidence=[])), "'evidence'"),
        (json.dumps(entry(id="Feynman 1982")), "DOI or arXiv"),
        (
            json.dumps(entry(evidence=[{"claim": "x", "quote": "0.5 K"}])),
            "at least 20",
        ),
        (
            json.dumps(entry(evidence=[{"claim": "x", "quote": "word " * 500}])),
            "at most 2000",
        ),
        (json.dumps(entry()) + "\n" + json.dumps(entry()), "line 2: duplicate key"),
    ],
)
def test_parse_sources_rejects_bad_input(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_sources(text, Path())


def test_parse_sources_rejects_more_than_the_limit() -> None:
    lines = [json.dumps(entry(key=f"k{n}", id=f"10.1000/k{n}")) for n in range(51)]
    with pytest.raises(ValueError, match="more than 50"):
        parse_sources("\n".join(lines), Path())


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("../outside.txt", "inside the folder"),
        ("paper.pdf", "PDF"),
    ],
)
def test_parse_sources_rejects_text_files_it_cannot_search(
    name: str, message: str, tmp_path: Path
) -> None:
    folder = tmp_path / "draft"
    folder.mkdir()
    (tmp_path / "outside.txt").write_text(FEYNMAN_QUOTE, encoding="utf-8")
    (folder / "paper.pdf").write_bytes(b"%PDF-1.7")
    evidence = [{"claim": "x", "quote": FEYNMAN_QUOTE, "text": name}]
    with pytest.raises(ValueError, match=message):
        sources(entry(evidence=evidence), base_dir=folder)


def test_parse_sources_bounds_the_total_saved_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text(FEYNMAN_QUOTE, encoding="utf-8")
    monkeypatch.setattr(verify_module, "MAX_SAVED_TEXT_BYTES", 60)
    evidence = [
        {"claim": "x", "quote": FEYNMAN_QUOTE, "text": name}
        for name in ("a.txt", "a.txt")
    ]
    sources(entry(evidence=evidence), base_dir=tmp_path)
    evidence[1]["text"] = "b.txt"
    with pytest.raises(ValueError, match="saved texts"):
        sources(entry(evidence=evidence), base_dir=tmp_path)


def test_parse_sources_rejects_one_work_cited_under_two_keys() -> None:
    text = (
        json.dumps(entry())
        + chr(10)
        + json.dumps(entry(key="Other", id="doi:10.1007/bf02650179"))
    )
    with pytest.raises(ValueError, match=r"line 2: .*also cited as Feynman1982"):
        parse_sources(text, Path())


def test_parse_sources_rejects_unreadable_text_file(tmp_path: Path) -> None:
    evidence = [{"claim": "x", "quote": FEYNMAN_QUOTE, "text": "missing.txt"}]
    with pytest.raises(ValueError, match=r"line 1: cannot read text file missing\.txt"):
        sources(entry(evidence=evidence), base_dir=tmp_path)


def test_parse_sources_accepts_numeric_volume_and_skips_blank_lines() -> None:
    (source,) = parse_sources("\n" + json.dumps(entry(volume=21)) + "\n\n", Path())
    assert source.volume == "21"


@pytest.mark.parametrize("argv", [["missing.jsonl"], ["bad.jsonl"]])
def test_main_exits_2_on_unreadable_or_invalid_input(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bad.jsonl").write_text("{not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(argv) == 2


# DOI records


def test_doi_matching_every_field_is_verified() -> None:
    verification = check({}, doi_registry())
    assert verification.status is Status.VERIFIED
    assert set(outcomes(verification).values()) == {Outcome.MATCH}
    assert verification.claims[0].found_in == "abstract (Crossref)"


@pytest.mark.parametrize(
    ("fields", "work", "field"),
    [
        ({"title": "Simulating physics with quantum computers"}, None, "title"),
        ({"authors": ["Feynman", "Wheeler"]}, None, "authors"),
        ({}, crossref(author=families("Feynman", "Wheeler")), "authors"),
        (
            {"authors": ["Jones", "Feynman"]},
            crossref(author=families("Feynman", "Jones")),
            "authors",
        ),
        ({"year": 1983}, None, "year"),
        ({"volume": "22"}, None, "volume"),
        ({"pages": "468"}, None, "first page"),
    ],
)
def test_doi_with_a_wrong_field_is_a_mismatch(
    fields: dict[str, object], work: bytes | None, field: str
) -> None:
    verification = check(fields, doi_registry(work))
    assert verification.status is Status.MISMATCH
    assert outcomes(verification)[field] is Outcome.MISMATCH


def test_et_al_needs_only_the_listed_authors_to_match() -> None:
    work = crossref(author=families("Feynman", "Wheeler", "Jones"))
    verification = check({"authors": ["Feynman", "et al."]}, doi_registry(work))
    assert outcomes(verification)["authors"] is Outcome.MATCH


def test_surnames_match_despite_accents_case_and_particles() -> None:
    work = crossref(author=families("de Gennes", "Schrödinger"))
    verification = check({"authors": ["De Gennes", "Schrodinger"]}, doi_registry(work))
    assert outcomes(verification)["authors"] is Outcome.MATCH


def test_title_matches_across_markup_and_punctuation() -> None:
    work = crossref(title=["Spin-<i>orbit</i> coupling in GaAs: a review"])
    verification = check(
        {"title": "Spin orbit coupling in GaAs. A review"}, doi_registry(work)
    )
    assert outcomes(verification)["title"] is Outcome.MATCH


def test_year_matches_the_print_year_when_issue_year_differs() -> None:
    verification = check(
        {"year": 1983},
        doi_registry(crossref(**{"published-print": {"date-parts": [[1983, 1]]}})),
    )
    assert outcomes(verification)["year"] is Outcome.MATCH


def test_article_number_stands_in_for_first_page() -> None:
    work = crossref(page=None, **{"article-number": "061102"})
    verification = check({"pages": "061102"}, doi_registry(work))
    assert outcomes(verification)["first page"] is Outcome.MATCH


@pytest.mark.parametrize(
    "pages", [f"467{chr(0x2013)}488", "pp. 467-488", "p 467", "467"]
)
def test_first_page_is_read_from_any_usual_page_range(pages: str) -> None:
    verification = check({"pages": pages}, doi_registry())
    assert outcomes(verification)["first page"] is Outcome.MATCH


def test_article_number_with_a_letter_prefix_is_kept_whole() -> None:
    work = crossref(page=None, **{"article-number": "P04005"})
    verification = check({"pages": "P04005"}, doi_registry(work))
    assert outcomes(verification)["first page"] is Outcome.MATCH


def test_angle_brackets_in_a_cited_title_are_text_not_markup() -> None:
    work = crossref(title=["Proof that a&lt;b and b&gt;c"])
    verification = check({"title": "Proof that a<b and b>c"}, doi_registry(work))
    assert outcomes(verification)["title"] is Outcome.MATCH


def test_work_without_authors_matches_an_empty_author_list() -> None:
    verification = check({"authors": []}, doi_registry(crossref(author=None)))
    assert outcomes(verification)["authors"] is Outcome.MATCH


def test_empty_author_list_is_a_mismatch_when_the_record_has_authors() -> None:
    verification = check({"authors": []}, doi_registry())
    assert outcomes(verification)["authors"] is Outcome.MISMATCH


def test_unstated_volume_and_pages_are_not_held_against_the_source() -> None:
    verification = check({"volume": None, "pages": None}, doi_registry())
    assert verification.status is Status.VERIFIED
    assert outcomes(verification)["volume"] is Outcome.NOT_GIVEN


def test_missing_doi_is_unverified() -> None:
    verification = check({}, datacite_registry(None))
    assert verification.status is Status.UNVERIFIED
    assert verification.reason == "no Crossref or DataCite record for this DOI"
    assert "api.datacite.org" in verification.query_url


def test_unreachable_registry_is_unverified_not_an_error() -> None:
    registry = FakeRegistry(
        [("api.crossref.org", RegistryUnavailableError("timed out"))]
    )
    verification = check({}, registry)
    assert verification.status is Status.UNVERIFIED
    assert "Crossref unavailable" in verification.reason


def test_unreadable_record_is_unverified() -> None:
    verification = check({}, doi_registry(b"<html>busy</html>"))
    assert verification.status is Status.UNVERIFIED


def test_crossref_retraction_wins_over_a_title_mismatch() -> None:
    work = crossref(
        title=["RETRACTED ARTICLE: Simulating physics with computers"],
        **notices(("retraction", "10.1/r"), ("retraction", "10.1/r")),
    )
    verification = check({}, doi_registry(work))
    assert verification.status is Status.RETRACTED
    assert outcomes(verification)["title"] is Outcome.MATCH
    assert len(verification.notices) == 1


def test_openalex_retraction_flag_is_enough() -> None:
    verification = check({}, doi_registry(alex=openalex(retracted=True)))
    assert verification.status is Status.RETRACTED


def test_correction_is_noted_without_changing_status() -> None:
    work = crossref(**notices(("correction", "10.1/c")))
    verification = check({}, doi_registry(work))
    assert verification.status is Status.VERIFIED
    assert [notice.retracts for notice in verification.notices] == [False]


def test_openalex_outage_is_recorded_and_not_fatal() -> None:
    registry = doi_registry(alex=RegistryUnavailableError("HTTP 503"))
    verification = check({}, registry)
    assert verification.status is Status.VERIFIED
    assert "OpenAlex unavailable" in verification.retraction_checked


@pytest.mark.parametrize(
    "body",
    [
        b'{"message": "oops"}',
        b"[1, 2]",
        b"[" * 100_000 + b"]" * 100_000,
    ],
    ids=["message-not-object", "not-object", "deeply-nested"],
)
def test_unexpected_crossref_shape_is_unverified(body: bytes) -> None:
    verification = check({}, FakeRegistry([("api.crossref.org", body)]))
    assert verification.status is Status.UNVERIFIED
    assert "Crossref returned" in verification.reason


def test_malformed_record_fields_are_skipped_not_fatal() -> None:
    work = crossref(
        issued={"date-parts": [[None]]},
        author={"family": "Feynman"},
        **{
            "published-print": {"date-parts": [[1982, 6]]},
            "updated-by": [{"type": "correction", "updated": "x"}, "junk"],
        },
    )
    verification = check({}, doi_registry(work))
    assert outcomes(verification)["year"] is Outcome.MATCH
    assert [notice.kind for notice in verification.notices] == ["correction"]


# DataCite records


def test_datacite_record_matching_every_field_is_verified() -> None:
    verification = check({}, datacite_registry(datacite()))
    assert verification.status is Status.VERIFIED
    assert set(outcomes(verification).values()) == {Outcome.MATCH}
    assert verification.claims[0].found_in == "abstract (DataCite)"
    assert verification.venue == "International Journal of Theoretical Physics"
    assert verification.version == "version of record"


def test_datacite_is_not_asked_when_crossref_has_the_record() -> None:
    registry = doi_registry()
    check({}, registry)
    assert not any("datacite" in url for url in registry.requested)


def test_datacite_unavailable_after_a_crossref_miss_is_unverified() -> None:
    registry = datacite_registry(RegistryUnavailableError("HTTP 503"))
    verification = check({}, registry)
    assert verification.status is Status.UNVERIFIED
    assert verification.reason.startswith("no Crossref record; DataCite unavailable")
    assert "HTTP 503" in verification.reason


def test_crossref_outage_does_not_fall_back_to_datacite() -> None:
    registry = FakeRegistry([("api.crossref.org", RegistryUnavailableError("x"))])
    verification = check({}, registry)
    assert "Crossref unavailable" in verification.reason


@pytest.mark.parametrize(
    "body",
    [b"<html>busy</html>", b'{"data": "oops"}', b"[1, 2]", b'{"data": {}}'],
    ids=["not-json", "data-not-object", "not-object", "no-attributes"],
)
def test_unreadable_datacite_record_is_unverified(body: bytes) -> None:
    verification = check({}, datacite_registry(body))
    assert verification.status is Status.UNVERIFIED
    assert verification.reason.startswith(
        "no Crossref record; DataCite returned an unreadable record"
    )


def test_malformed_datacite_fields_are_skipped_not_fatal() -> None:
    record = datacite(
        titles=[
            "junk",
            {"title": 5},
            {"title": "Simulating physics with computers"},
            {"title": "Ignored translation", "titleType": "TranslatedTitle"},
        ],
        creators=[7, {"name": "Feynman"}],
        publicationYear="1982",
        container=["not", "an", "object"],
        publisher={"name": "Springer"},
        descriptions=[None, {"description": 3, "descriptionType": "Abstract"}],
    )
    verification = check({}, datacite_registry(record))
    assert outcomes(verification)["title"] is Outcome.MATCH
    assert outcomes(verification)["authors"] is Outcome.MATCH
    assert outcomes(verification)["year"] is Outcome.MATCH
    assert outcomes(verification)["volume"] is Outcome.NOT_IN_RECORD
    assert verification.venue == "Springer"
    assert verification.status is Status.CLAIM_NOT_CHECKED


@pytest.mark.parametrize("year", [None, True, "nineteen", [1982]])
def test_unusable_datacite_year_is_a_mismatch_not_a_crash(year: object) -> None:
    verification = check({}, datacite_registry(datacite(publicationYear=year)))
    assert outcomes(verification)["year"] is Outcome.MISMATCH


def test_datacite_subtitle_is_part_of_the_title() -> None:
    record = datacite(
        titles=[
            {"title": "Simulating physics"},
            {"title": "with computers", "titleType": "Subtitle"},
        ]
    )
    verification = check({}, datacite_registry(record))
    assert outcomes(verification)["title"] is Outcome.MATCH


def test_datacite_surname_falls_back_to_the_name() -> None:
    record = datacite(creators=[{"name": "Feynman"}])
    verification = check({}, datacite_registry(record))
    assert outcomes(verification)["authors"] is Outcome.MATCH


def test_datacite_surname_is_read_from_a_family_first_name() -> None:
    record = datacite(creators=[{"name": "Feynman, Richard P."}])
    verification = check({}, datacite_registry(record))
    assert outcomes(verification)["authors"] is Outcome.MATCH


def test_datacite_organisation_name_is_kept_whole() -> None:
    record = datacite(
        creators=[{"name": "ATLAS Collaboration, CERN", "nameType": "Organizational"}]
    )
    verification = check(
        {"authors": ["ATLAS Collaboration, CERN"]}, datacite_registry(record)
    )
    assert outcomes(verification)["authors"] is Outcome.MATCH


def test_datacite_record_is_enriched_with_openalex() -> None:
    registry = datacite_registry(datacite(), alex=openalex(retracted=True))
    verification = check({}, registry)
    assert verification.status is Status.RETRACTED


def test_retraction_column_names_datacite_and_openalex() -> None:
    verification = check({}, datacite_registry(datacite()))
    assert verification.retraction_checked == "DataCite and OpenAlex"
    row = log_row(verification, date(2026, 11, 8))
    assert "none found in DataCite and OpenAlex on 2026-11-08" in row


def test_retraction_column_records_an_openalex_outage_after_datacite() -> None:
    registry = datacite_registry(datacite(), alex=RegistryUnavailableError("HTTP 503"))
    verification = check({}, registry)
    assert verification.status is Status.VERIFIED
    assert verification.retraction_checked.startswith("DataCite; OpenAlex unavailable")


# Quoted passages


def test_quote_found_in_openalex_abstract_when_crossref_has_none() -> None:
    registry = doi_registry(
        crossref(abstract=None), openalex(abstract="Thus " + FEYNMAN_QUOTE)
    )
    verification = check({}, registry)
    assert verification.claims[0].found_in == "abstract (OpenAlex)"


def test_quote_matches_despite_typographic_differences() -> None:
    abstract = "<p>The \ufb01t gives \u201cT = \u22120.5 K\u201d at\n  low field.</p>"
    quote = 'The fit gives "T = -0.5 K" at low field.'
    evidence = [{"claim": "The fit gives a negative temperature.", "quote": quote}]
    verification = check(
        {"evidence": evidence}, doi_registry(crossref(abstract=abstract))
    )
    assert verification.status is Status.VERIFIED


def test_quote_absent_from_text_read_leaves_claim_not_checked() -> None:
    evidence = [
        {"claim": "x", "quote": "Quantum computers will replace all classical ones."}
    ]
    verification = check({"evidence": evidence}, doi_registry())
    assert verification.status is Status.CLAIM_NOT_CHECKED
    assert verification.claims[0].found_in is None


MISSING_QUOTE = [
    {"claim": "Computers will replace all.", "quote": "Quantum computers will win."}
]
FULL_TEXT_URL = "https://example.org/feynman.pdf"


def row_for(verification: Verification) -> str:
    return log_row(verification, date(2026, 11, 8))


def test_missing_quote_row_links_openalex_open_access_text() -> None:
    registry = doi_registry(alex=openalex(oa_url=FULL_TEXT_URL))
    row = row_for(check({"evidence": MISSING_QUOTE}, registry))
    assert (
        "Computers will replace all. (quote not found in the text read; "
        f"full text may be at {FULL_TEXT_URL})"
    ) in row


def test_found_quote_row_does_not_link_open_access_text() -> None:
    registry = doi_registry(alex=openalex(oa_url=FULL_TEXT_URL))
    row = row_for(check({}, registry))
    assert FULL_TEXT_URL not in row
    assert "full text may be" not in row


def test_missing_quote_without_open_access_text_is_unchanged() -> None:
    row = row_for(check({"evidence": MISSING_QUOTE}, doi_registry()))
    assert "(quote not found in the text read)" in row
    assert "full text may be" not in row


@pytest.mark.parametrize("oa_url", ["ftp://x", 42, ["https://x.org"], ""])
def test_open_access_url_that_is_not_http_gives_no_link(oa_url: object) -> None:
    registry = doi_registry(alex=openalex(oa_url=oa_url))
    row = row_for(check({"evidence": MISSING_QUOTE}, registry))
    assert "(quote not found in the text read)" in row


def test_openalex_outage_gives_no_link_and_no_error() -> None:
    registry = doi_registry(alex=RegistryUnavailableError("HTTP 503"))
    verification = check({"evidence": MISSING_QUOTE}, registry)
    assert verification.status is Status.CLAIM_NOT_CHECKED
    assert "full text may be" not in row_for(verification)


def test_pipe_in_open_access_url_is_escaped() -> None:
    registry = doi_registry(alex=openalex(oa_url="https://example.org/a|b"))
    row = row_for(check({"evidence": MISSING_QUOTE}, registry))
    assert "https://example.org/a\\|b)" in row


def test_datacite_source_with_missing_quote_links_openalex_text() -> None:
    registry = datacite_registry(datacite(), openalex(oa_url=FULL_TEXT_URL))
    row = row_for(check({"evidence": MISSING_QUOTE}, registry))
    assert f"full text may be at {FULL_TEXT_URL})" in row


def test_unchecked_source_has_no_open_text() -> None:
    verification = check({}, datacite_registry(None))
    assert verification.open_text is None


def test_quote_is_case_sensitive() -> None:
    evidence = [{"claim": "x", "quote": FEYNMAN_QUOTE.upper()}]
    verification = check({"evidence": evidence}, doi_registry())
    assert verification.status is Status.CLAIM_NOT_CHECKED


def test_quote_found_in_saved_html_text(tmp_path: Path) -> None:
    page = (
        "<html><head><title>x</title><style>p {}</style></head><body>"
        "<script>var hidden = 'Results show a 3.2 K shift';</script>"
        "<p>Results show a 3.2&nbsp;K shift</p><p>in the critical temperature.</p>"
        "</body></html>"
    )
    (tmp_path / "paper.html").write_text(page, encoding="utf-8")
    evidence = [
        {
            "claim": "x",
            "quote": "Results show a 3.2 K shift in the critical",
            "text": "paper.html",
        }
    ]
    (source,) = sources(entry(evidence=evidence), base_dir=tmp_path)
    verification = verify(source, doi_registry())
    assert verification.claims[0].found_in == "saved text paper.html"


def test_saved_html_with_unclosed_head_is_still_searched(tmp_path: Path) -> None:
    page = "<html><head><title>t</title><body><p>Results show a 3.2 K shift in Tc</p>"
    (tmp_path / "paper.html").write_text(page, encoding="utf-8")
    evidence = [
        {"claim": "x", "quote": "Results show a 3.2 K shift", "text": "paper.html"}
    ]
    (source,) = sources(entry(evidence=evidence), base_dir=tmp_path)
    assert verify(source, doi_registry()).claims[0].found_in == "saved text paper.html"


def test_script_text_in_saved_html_is_not_searched(tmp_path: Path) -> None:
    page = (
        "<script>var s = 'Results show a 3.2 K shift in the critical';</script><p>x</p>"
    )
    (tmp_path / "paper.htm").write_text(page, encoding="utf-8")
    evidence = [
        {
            "claim": "x",
            "quote": "Results show a 3.2 K shift in the critical",
            "text": "paper.htm",
        }
    ]
    (source,) = sources(entry(evidence=evidence), base_dir=tmp_path)
    assert verify(source, doi_registry()).claims[0].found_in is None


# arXiv records


def arxiv_entry(**fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "key": "Vaswani2017",
        "id": "arXiv:1706.03762",
        "title": "Attention is all you need",
        "authors": ["Vaswani", "Shazeer", "Parmar"],
        "year": 2017,
        "evidence": [{"claim": "x", "quote": ATTENTION_V7}],
    }
    base.update(fields)
    return base


def check_arxiv(fields: dict[str, object], registry: FakeRegistry) -> Verification:
    (source,) = sources(arxiv_entry(**fields))
    return verify(source, registry)


def test_arxiv_latest_version_is_verified() -> None:
    registry = FakeRegistry(
        [("id_list=1706.03762", atom(version=7, summary=ATTENTION_V7))]
    )
    verification = check_arxiv({}, registry)
    assert verification.status is Status.VERIFIED
    assert verification.version == "v7 (latest)"
    assert outcomes(verification)["volume"] is Outcome.NOT_GIVEN


def test_arxiv_cited_version_is_read_and_drift_is_reported() -> None:
    registry = FakeRegistry(
        [
            ("id_list=1706.03762v1", atom(version=1, summary=ATTENTION_V1)),
            ("id_list=1706.03762", atom(version=7, summary=ATTENTION_V7)),
        ]
    )
    verification = check_arxiv(
        {"id": "1706.03762v1", "evidence": [{"claim": "x", "quote": ATTENTION_V1}]},
        registry,
    )
    assert verification.status is Status.VERIFIED
    assert verification.claims[0].found_in == "abstract (arXiv v1)"
    assert "latest is v7" in verification.version


def test_arxiv_quote_from_another_version_is_not_checked() -> None:
    registry = FakeRegistry(
        [
            ("id_list=1706.03762v1", atom(version=1, summary=ATTENTION_V1)),
            ("id_list=1706.03762", atom(version=7, summary=ATTENTION_V7)),
        ]
    )
    verification = check_arxiv({"id": "1706.03762v1"}, registry)
    assert verification.status is Status.CLAIM_NOT_CHECKED


def test_arxiv_missing_quote_row_links_abstract_page_of_latest_version() -> None:
    registry = FakeRegistry(
        [("id_list=1706.03762", atom(version=7, summary=ATTENTION_V7))]
    )
    row = row_for(check_arxiv({"evidence": MISSING_QUOTE}, registry))
    assert "full text may be at https://arxiv.org/abs/1706.03762v7)" in row


def test_arxiv_missing_quote_row_links_the_cited_older_version() -> None:
    registry = FakeRegistry(
        [
            ("id_list=1706.03762v1", atom(version=1, summary=ATTENTION_V1)),
            ("id_list=1706.03762", atom(version=7, summary=ATTENTION_V7)),
        ]
    )
    row = row_for(check_arxiv({"id": "1706.03762v1"}, registry))
    assert "full text may be at https://arxiv.org/abs/1706.03762v1)" in row


def test_arxiv_old_style_identifier_link_keeps_archive_and_number() -> None:
    registry = FakeRegistry(
        [("id_list=hep-th/9901001", atom(version=2, summary=ATTENTION_V7))]
    )
    row = row_for(
        check_arxiv({"id": "hep-th/9901001", "evidence": MISSING_QUOTE}, registry)
    )
    assert "full text may be at https://arxiv.org/abs/hep-th/9901001v2)" in row


def test_arxiv_found_quote_row_has_no_link() -> None:
    registry = FakeRegistry(
        [("id_list=1706.03762", atom(version=7, summary=ATTENTION_V7))]
    )
    assert "arxiv.org/abs" not in row_for(check_arxiv({}, registry))


def test_arxiv_journal_version_is_reported() -> None:
    feed = atom(
        version=2,
        summary=ATTENTION_V7,
        extras="<arxiv:journal_ref>Phys. Rev. D 99, 1 (2019)</arxiv:journal_ref>",
    )
    verification = check_arxiv({}, FakeRegistry([("id_list=1706.03762", feed)]))
    assert "Phys. Rev. D 99, 1 (2019)" in verification.version


def test_arxiv_withdrawn_paper_is_retracted() -> None:
    feed = atom(
        version=3,
        summary=ATTENTION_V7,
        extras="<arxiv:comment>This paper has been withdrawn</arxiv:comment>",
    )
    verification = check_arxiv({}, FakeRegistry([("id_list=1706.03762", feed)]))
    assert verification.status is Status.RETRACTED


@pytest.mark.parametrize(
    ("comment", "status"),
    [
        ("Withdrawn: duplicate of arXiv:1601.00001", Status.RETRACTED),
        ("This submission has been withdrawn by arXiv admin", Status.RETRACTED),
        ("Supersedes the withdrawn preprint arXiv:1601.00001", Status.VERIFIED),
    ],
)
def test_arxiv_withdrawal_is_read_from_the_comment_not_any_mention(
    comment: str, status: Status
) -> None:
    feed = atom(
        version=2,
        summary=ATTENTION_V7,
        extras=f"<arxiv:comment>{comment}</arxiv:comment>",
    )
    verification = check_arxiv({}, FakeRegistry([("id_list=1706.03762", feed)]))
    assert verification.status is status


def test_arxiv_missing_identifier_is_unverified() -> None:
    verification = check_arxiv(
        {"id": "2401.99999"}, FakeRegistry([("id_list=2401.99999", EMPTY_ATOM)])
    )
    assert verification.status is Status.UNVERIFIED
    assert "no arXiv paper" in verification.reason


def test_arxiv_missing_cited_version_is_unverified() -> None:
    registry = FakeRegistry(
        [
            ("id_list=1706.03762v9", EMPTY_ATOM),
            ("id_list=1706.03762", atom(version=7, summary=ATTENTION_V7)),
        ]
    )
    verification = check_arxiv({"id": "1706.03762v9"}, registry)
    assert verification.status is Status.UNVERIFIED


def test_arxiv_authors_match_on_surname_from_full_name() -> None:
    feed = atom(version=1, summary=ATTENTION_V7, authors=("Pierre-Gilles de Gennes",))
    verification = check_arxiv(
        {"authors": ["de Gennes"]}, FakeRegistry([("id_list=1706.03762", feed)])
    )
    assert outcomes(verification)["authors"] is Outcome.MATCH


def test_arxiv_malformed_dates_are_skipped_not_fatal() -> None:
    feed = atom(version=1, summary=ATTENTION_V7).replace(
        b"<published>2017-06-12T17:57:34Z", b"<published>unknown"
    )
    verification = check_arxiv({}, FakeRegistry([("id_list=1706.03762", feed)]))
    assert outcomes(verification)["year"] is Outcome.MATCH


def test_arxiv_unreachable_is_unverified() -> None:
    registry = FakeRegistry([("arxiv.org", RegistryUnavailableError("HTTP 503"))])
    assert check_arxiv({}, registry).status is Status.UNVERIFIED


# Log


def test_log_has_one_row_per_source_and_escapes_pipes() -> None:
    registry = doi_registry(crossref(title=["A | B"]))
    first, second = sources(
        entry(title="A | B"),
        entry(key="Missing", id="10.9999/none"),
    )
    missing = verify(second, datacite_registry(None))
    verifications = [verify(first, registry), missing]
    rows = [log_row(v, date(2026, 11, 8)) for v in verifications]
    header, rule = LOG_HEADER.splitlines()
    columns = header.count(" | ")
    assert rule.count("|") == header.count("|")
    assert all(row.replace("\\|", "").count(" | ") == columns for row in rows)
    assert "A \\| B" in rows[0]
    assert "2026-11-08" in rows[0]
    assert log_summary(verifications) == "1 of 2 sources verified."


# Command line


def test_main_reads_and_writes_utf8_whatever_the_console_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line = json.dumps(entry(authors=["Schr\u00f6dinger"]), ensure_ascii=False)
    stdin = io.TextIOWrapper(io.BytesIO(line.encode()), encoding="cp1252")
    written = io.BytesIO()
    stdout = io.TextIOWrapper(written, encoding="cp1252")
    registry = doi_registry(crossref(author=families("Schr\u00f6dinger")))
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(verify_module, "RegistryClient", lambda: registry)
    assert main(["-"]) == 0
    stdout.flush()
    log = written.getvalue().decode("utf-8")
    assert "Schr\u00f6dinger" in log
    assert "| VERIFIED |" in log


def test_main_exits_2_on_input_nested_too_deeply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "deep.jsonl").write_text("[" * 100_000, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["deep.jsonl"]) == 2


def test_main_exits_3_on_a_fault_and_keeps_rows_already_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = [json.dumps(entry()), json.dumps(entry(key="Second", id="10.1000/second"))]
    (tmp_path / "sources.jsonl").write_text(chr(10).join(lines), encoding="utf-8")
    registry = FakeRegistry(
        [
            ("10.1000/second", RuntimeError("bug")),
            ("api.crossref.org", crossref()),
            ("api.openalex.org", openalex()),
        ]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(verify_module, "RegistryClient", lambda: registry)
    assert main(["sources.jsonl"]) == 3
    captured = capsys.readouterr()
    assert "| Feynman1982 |" in captured.out
    assert "Second" in captured.err


def test_main_stops_checking_at_the_run_time_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sources.jsonl").write_text(json.dumps(entry()), encoding="utf-8")
    registry = doi_registry()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(verify_module, "RegistryClient", lambda: registry)
    monkeypatch.setattr(verify_module, "MAX_RUN_SECONDS", -1)
    assert main(["sources.jsonl"]) == 1
    assert registry.requested == []
    assert "run time limit" in capsys.readouterr().out


# Registry client


class FakeNetwork:
    """Stands in for urlopen and the clock: answers in order, records sleeps."""

    def __init__(self, answers: Sequence[bytes | Exception]) -> None:
        self.answers = list(answers)
        self.urls: list[str] = []
        self.slept: list[float] = []
        self.now = 1000.0

    def urlopen(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
        assert timeout > 0
        self.urls.append(request.full_url)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return io.BytesIO(answer)

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://x", code, "error", headers, None)


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> FakeNetwork:
    fake = FakeNetwork([])
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    monkeypatch.setattr(time, "sleep", fake.sleep)
    monkeypatch.setattr(time, "monotonic", fake.monotonic)
    return fake


CROSSREF_URL = "https://api.crossref.org/works/10.1000/x"
ARXIV_URL = "https://export.arxiv.org/api/query?id_list=1706.03762"


def test_client_returns_none_for_not_found(network: FakeNetwork) -> None:
    network.answers = [http_error(404)]
    assert RegistryClient()(CROSSREF_URL) is None


def test_client_retries_a_busy_registry_then_answers(network: FakeNetwork) -> None:
    network.answers = [http_error(503), http.client.IncompleteRead(b""), b"ok"]
    assert RegistryClient()(CROSSREF_URL) == b"ok"
    assert len(network.slept) == 2


def test_client_caps_the_wait_a_registry_asks_for(network: FakeNetwork) -> None:
    network.answers = [http_error(429, retry_after="999"), b"ok"]
    RegistryClient()(CROSSREF_URL)
    assert network.slept == [verify_module.MAX_RETRY_WAIT_SECONDS]


def test_client_gives_up_after_the_last_attempt(network: FakeNetwork) -> None:
    network.answers = [http_error(503)] * verify_module.MAX_ATTEMPTS
    with pytest.raises(RegistryUnavailableError, match="HTTP 503"):
        RegistryClient()(CROSSREF_URL)


def test_client_does_not_retry_a_refused_request(network: FakeNetwork) -> None:
    network.answers = [http_error(400), b"never sent"]
    with pytest.raises(RegistryUnavailableError, match="HTTP 400"):
        RegistryClient()(CROSSREF_URL)
    assert network.slept == []


def test_client_refuses_an_oversized_response(
    network: FakeNetwork, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(verify_module, "MAX_RESPONSE_BYTES", 4)
    network.answers = [b"12345"]
    with pytest.raises(RegistryUnavailableError, match="over 4 bytes"):
        RegistryClient()(CROSSREF_URL)


def test_client_spaces_arxiv_requests_but_not_others(network: FakeNetwork) -> None:
    network.answers = [b"a", b"b", b"c"]
    client = RegistryClient()
    client(ARXIV_URL)
    client(CROSSREF_URL)
    client(ARXIV_URL)
    assert network.slept == [verify_module.ARXIV_INTERVAL_SECONDS]


def test_main_exits_2_on_oversized_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sources.jsonl").write_text(json.dumps(entry()), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(verify_module, "MAX_INPUT_CHARACTERS", 10)
    assert main(["sources.jsonl"]) == 2


# Response cache


URL = "https://api.example.org/works/1"
OTHER_URL = "https://api.example.org/works/2"
START = 1_000_000.0


class FakeClock:
    def __init__(self, now: float = START) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def cache_over(
    registry: FakeRegistry,
    path: Path,
    clock: FakeClock,
    *,
    refresh: bool = False,
) -> ResponseCache:
    return ResponseCache(registry, path, now=clock, refresh=refresh)


def encoded(body: bytes | None) -> str | None:
    return None if body is None else base64.b64encode(body).decode("ascii")


def write_cache(
    path: Path, entries: dict[str, object], fmt: str = CACHE_FORMAT
) -> None:
    path.write_text(json.dumps({"format": fmt, "entries": entries}), encoding="utf-8")


def stored_urls(path: Path) -> set[str]:
    return set(json.loads(path.read_text(encoding="utf-8"))["entries"])


def test_cache_answers_a_repeat_lookup_without_a_request(tmp_path: Path) -> None:
    registry = FakeRegistry([("example.org", b"body")])
    cache = cache_over(registry, tmp_path / "c.json", FakeClock())
    assert cache(URL) == b"body"
    assert cache(URL) == b"body"
    assert registry.requested == [URL]


def test_cache_answers_from_the_file_written_by_an_earlier_run(
    tmp_path: Path,
) -> None:
    path = tmp_path / "c.json"
    first = FakeRegistry([("example.org", b"body")])
    writer = cache_over(first, path, FakeClock())
    writer(URL)
    writer.save()
    second = FakeRegistry([])
    clock = FakeClock(START + 60)
    assert cache_over(second, path, clock)(URL) == b"body"
    assert second.requested == []


def test_cache_fetches_again_after_the_lifetime(tmp_path: Path) -> None:
    registry = FakeRegistry([("example.org", b"body")])
    clock = FakeClock()
    cache = cache_over(registry, tmp_path / "c.json", clock)
    cache(URL)
    clock.now += CACHE_LIFETIME_SECONDS - 1
    cache(URL)
    assert registry.requested == [URL]
    clock.now = START + CACHE_LIFETIME_SECONDS
    cache(URL)
    assert registry.requested == [URL, URL]


def test_cache_treats_a_future_timestamp_as_expired(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    write_cache(path, {URL: {"fetched": START + 5, "body": encoded(b"old")}})
    registry = FakeRegistry([("example.org", b"new")])
    assert cache_over(registry, path, FakeClock())(URL) == b"new"
    assert registry.requested == [URL]


def test_refresh_fetches_despite_a_fresh_entry_and_stores_the_new_body(
    tmp_path: Path,
) -> None:
    path = tmp_path / "c.json"
    write_cache(path, {URL: {"fetched": START, "body": encoded(b"old")}})
    registry = FakeRegistry([("example.org", b"new")])
    refreshing = cache_over(registry, path, FakeClock(), refresh=True)
    assert refreshing(URL) == b"new"
    refreshing.save()
    later = FakeRegistry([])
    assert cache_over(later, path, FakeClock())(URL) == b"new"
    assert later.requested == []


def test_cache_remembers_a_404(tmp_path: Path) -> None:
    registry = FakeRegistry([("example.org", None)])
    cache = cache_over(registry, tmp_path / "c.json", FakeClock())
    assert cache(URL) is None
    assert cache(URL) is None
    assert registry.requested == [URL]


def test_cache_returns_but_does_not_store_a_body_over_the_limit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "c.json"
    big = b"x" * (MAX_CACHED_BODY_BYTES + 1)
    registry = FakeRegistry([("example.org", big)])
    cache = cache_over(registry, path, FakeClock())
    assert cache(URL) == big
    cache.save()
    assert stored_urls(path) == set()
    cache(URL)
    assert registry.requested == [URL, URL]


def test_cache_stores_a_body_at_the_limit(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    registry = FakeRegistry([("example.org", b"x" * MAX_CACHED_BODY_BYTES)])
    cache = cache_over(registry, path, FakeClock())
    cache(URL)
    cache.save()
    assert stored_urls(path) == {URL}


def test_cache_propagates_a_failure_and_stores_nothing(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    registry = FakeRegistry([("example.org", RegistryUnavailableError("down"))])
    cache = cache_over(registry, path, FakeClock())
    with pytest.raises(RegistryUnavailableError):
        cache(URL)
    cache.save()
    assert stored_urls(path) == set()


def test_save_leaves_out_expired_entries(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    write_cache(
        path,
        {
            URL: {"fetched": START - CACHE_LIFETIME_SECONDS - 1, "body": None},
            OTHER_URL: {"fetched": START - 10, "body": None},
        },
    )
    cache = cache_over(FakeRegistry([]), path, FakeClock())
    cache.save()
    assert stored_urls(path) == {OTHER_URL}


def test_save_writes_the_format_marker_and_leaves_no_temporary_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "c.json"
    cache = cache_over(FakeRegistry([("example.org", b"b")]), path, FakeClock())
    cache(URL)
    cache.save()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["format"] == CACHE_FORMAT
    assert written["entries"][URL] == {"fetched": START, "body": encoded(b"b")}
    assert [p.name for p in tmp_path.iterdir()] == ["c.json"]


def test_a_missing_cache_file_starts_empty_without_a_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = FakeRegistry([("example.org", b"body")])
    assert cache_over(registry, tmp_path / "c.json", FakeClock())(URL) == b"body"
    assert capsys.readouterr().err == ""


def _corrupt(path: Path) -> None:
    path.write_text("{not json", encoding="utf-8")


def _foreign(path: Path) -> None:
    write_cache(path, {URL: {"fetched": START, "body": None}}, fmt="other/1")


def _wrong_shape(path: Path) -> None:
    path.write_text(
        json.dumps({"format": CACHE_FORMAT, "entries": []}), encoding="utf-8"
    )


def _oversized(path: Path) -> None:
    write_cache(path, {URL: {"fetched": START, "body": encoded(b"x" * 100)}})


@pytest.mark.parametrize("damage", [_corrupt, _foreign, _wrong_shape, _oversized])
def test_an_unusable_cache_file_is_reported_ignored_and_replaced(
    damage: Callable[[Path], None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "c.json"
    damage(path)
    if damage is _oversized:
        monkeypatch.setattr(verify_module, "MAX_CACHE_FILE_BYTES", 50)
    registry = FakeRegistry([("example.org", b"body")])
    cache = cache_over(registry, path, FakeClock())
    assert cache(URL) == b"body"
    assert registry.requested == [URL]
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert str(path) in err
    cache.save()
    assert stored_urls(path) == {URL}


def test_an_unreadable_cache_path_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "c.json"
    path.mkdir()
    registry = FakeRegistry([("example.org", b"body")])
    assert cache_over(registry, path, FakeClock())(URL) == b"body"
    assert str(path) in capsys.readouterr().err


def test_a_malformed_entry_is_skipped_while_good_ones_load(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "c.json"
    good = {"fetched": START, "body": encoded(b"good")}
    write_cache(
        path,
        {
            "https://e/bad-base64": {"fetched": START, "body": "!!not base64!!"},
            "https://e/bad-time": {"fetched": "yesterday", "body": None},
            "https://e/bad-body": {"fetched": START, "body": 7},
            "https://e/not-a-dict": 3,
            "https://e/bool-time": {"fetched": True, "body": None},
            URL: good,
        },
    )
    registry = FakeRegistry([("https://e/", b"fresh")])
    cache = cache_over(registry, path, FakeClock())
    assert cache(URL) == b"good"
    assert cache("https://e/bad-time") == b"fresh"
    assert capsys.readouterr().err == ""


# Cache in the command line


def run_main_with(
    registry: FakeRegistry, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> int:
    monkeypatch.setattr(verify_module, "RegistryClient", lambda: registry)
    return main(argv)


def test_main_writes_the_cache_beside_the_sources_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "drafts"
    folder.mkdir()
    (folder / "refs.jsonl").write_text(json.dumps(entry()), encoding="utf-8")
    argv = [str(folder / "refs.jsonl")]
    assert run_main_with(doi_registry(), monkeypatch, argv) == 0
    assert (folder / "refs.cache.json").is_file()


def test_main_rerun_makes_no_repeat_requests_and_refresh_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_file = str(tmp_path / "refs.jsonl")
    (tmp_path / "refs.jsonl").write_text(json.dumps(entry()), encoding="utf-8")
    first = doi_registry()
    run_main_with(first, monkeypatch, [sources_file])
    second = doi_registry()
    assert run_main_with(second, monkeypatch, [sources_file]) == 0
    assert second.requested == []
    third = doi_registry()
    assert run_main_with(third, monkeypatch, [sources_file, "--refresh"]) == 0
    assert third.requested == first.requested


def test_main_makes_no_cache_for_standard_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(entry())))
    assert run_main_with(doi_registry(), monkeypatch, ["-"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_main_writes_the_cache_when_the_run_stops_on_a_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines = [json.dumps(entry()), json.dumps(entry(key="Second", id="10.1000/second"))]
    (tmp_path / "refs.jsonl").write_text("\n".join(lines), encoding="utf-8")
    registry = FakeRegistry(
        [
            ("10.1000/second", RuntimeError("bug")),
            ("api.crossref.org", crossref()),
            ("api.openalex.org", openalex()),
        ]
    )
    assert run_main_with(registry, monkeypatch, [str(tmp_path / "refs.jsonl")]) == 3
    assert (tmp_path / "refs.cache.json").is_file()


def test_main_keeps_its_exit_code_when_the_cache_cannot_be_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "refs.jsonl").write_text(json.dumps(entry()), encoding="utf-8")
    (tmp_path / "refs.cache.json").mkdir()
    argv = [str(tmp_path / "refs.jsonl")]
    assert run_main_with(doi_registry(), monkeypatch, argv) == 0
    assert "refs.cache.json" in capsys.readouterr().err
