import io
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
import verify as verify_module
from verify import (
    LOG_HEADER,
    ArxivId,
    CitedSource,
    Fetch,
    Outcome,
    RegistryUnavailableError,
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


def openalex(*, retracted: bool = False, abstract: str | None = None) -> bytes:
    index: dict[str, list[int]] = {}
    for position, word in enumerate((abstract or "").split()):
        index.setdefault(word, []).append(position)
    return json.dumps(
        {"is_retracted": retracted, "abstract_inverted_index": index or None}
    ).encode()


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
    lines = [json.dumps(entry(key=f"k{n}")) for n in range(51)]
    with pytest.raises(ValueError, match="more than 50"):
        parse_sources("\n".join(lines), Path())


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
    registry = FakeRegistry([("api.crossref.org", None)])
    verification = check({}, registry)
    assert verification.status is Status.UNVERIFIED
    assert "no Crossref record" in verification.reason


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
    missing = verify(second, FakeRegistry([("api.crossref.org", None)]))
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
