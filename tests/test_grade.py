import json
from pathlib import Path

import pytest
from grade import (
    AUTO_PREFIX,
    DEFAULT_EVALS,
    Check,
    CheckerClean,
    ContainsAny,
    EvalCase,
    ForbiddenPhrases,
    MaxHashtags,
    MaxOneSentenceParagraphShare,
    MaxWords,
    NumbersFromInputs,
    load_cases,
    main,
    score,
)

INPUTS = "Peaks at 7.1 and 12.0 V across 6,000 images on 17 November."


def scored(check: Check, deliverable: str) -> bool:
    return score(check, deliverable, INPUTS).passed


@pytest.mark.parametrize(
    ("check", "deliverable", "expected"),
    [
        (MaxWords(4), "One two three four.", True),
        (MaxWords(3), "One two three four.", False),
        (ForbiddenPhrases(("delve",)), "We measured the peaks.", True),
        (ForbiddenPhrases(("delve",)), "We Delve into the peaks.", False),
        (ContainsAny(("[DATA NEEDED",)), "Slope [DATA NEEDED: error].", True),
        (ContainsAny(("[DATA NEEDED",)), "Slope 4.90 V.", False),
        (MaxHashtags(2), "Done. #physics #ml", True),
        (MaxHashtags(1), "Done. #physics #ml", False),
        (MaxHashtags(0), "# Heading\n\nIssue C# and item #3.", True),
        (NumbersFromInputs(), "Peaks at 7.1 V and 12.0 V.", True),
        (NumbersFromInputs(), "Peaks at 7.2 V.", False),
        (NumbersFromInputs(), "We used 6000 images.", True),
        (NumbersFromInputs(), "On 17 November we ran 3 fits.", True),
        (NumbersFromInputs(), "Accuracy was 94.1%.", False),
        (NumbersFromInputs(), "[UNVERIFIED: no record on 2026-11-11]", True),
    ],
)
def test_text_checks_pass_and_fail(
    check: Check, deliverable: str, *, expected: bool
) -> None:
    assert scored(check, deliverable) is expected


def test_missing_numbers_are_named_in_the_evidence() -> None:
    result = score(NumbersFromInputs(), "Values 7.1, 7.2 and 94.1.", INPUTS)
    assert "7.2" in result.evidence
    assert "94.1" in result.evidence
    assert "7.1," not in result.evidence


def test_short_paragraph_share_counts_single_sentence_paragraphs() -> None:
    post = "One line.\n\nTwo sentences here. And here.\n\nAnother line.\n\n#tag"
    assert not scored(MaxOneSentenceParagraphShare(0.5), post)
    assert scored(MaxOneSentenceParagraphShare(0.75), post)


def test_short_paragraph_share_skips_headings_and_lists() -> None:
    post = "# Title\n\n- item\n- item\n\nFirst sentence. Second sentence."
    assert scored(MaxOneSentenceParagraphShare(0.0), post)


@pytest.mark.parametrize(
    ("deliverable", "expected"),
    [("We measured the peaks.", True), ("We measured the peaks \u2014 twice.", False)],
)
def test_checker_clean_runs_the_skill_checker(
    deliverable: str, *, expected: bool
) -> None:
    assert scored(CheckerClean("plain"), deliverable) is expected


def test_expectation_text_is_marked_as_automatic() -> None:
    assert score(MaxWords(5), "word", INPUTS).text.startswith(AUTO_PREFIX)


def write_evals(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    (tmp_path / "files").mkdir(exist_ok=True)
    (tmp_path / "files" / "notes.md").write_text("Slope 4.90 V.", encoding="utf-8")
    path = tmp_path / "evals.json"
    path.write_text(
        json.dumps({"skill_name": "writing", "evals": cases}), encoding="utf-8"
    )
    return path


def case(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "id": 1,
        "prompt": "Write up notes.md by 17 November.",
        "expected_output": "A results paragraph.",
        "files": ["files/notes.md"],
        "expectations": ["The slope is reported with its unit"],
        "checks": [{"kind": "max_words", "limit": 50}, {"kind": "numbers_from_inputs"}],
    }
    fields.update(overrides)
    return fields


def test_load_cases_reads_checks_and_input_text(tmp_path: Path) -> None:
    cases = load_cases(write_evals(tmp_path, [case()]))
    loaded = cases[1]
    assert isinstance(loaded, EvalCase)
    assert loaded.checks == (MaxWords(50), NumbersFromInputs())
    assert "4.90" in loaded.input_text
    assert "17 November" in loaded.input_text


@pytest.mark.parametrize(
    ("cases", "message"),
    [
        ([case(), case()], "duplicate eval id 1"),
        ([case(checks=[{"kind": "rhyme"}])], "unknown check kind 'rhyme'"),
        ([case(files=["files/absent.md"])], "absent.md"),
        ([case(checks=[{"kind": "max_words"}])], "limit"),
        ([case(expectations="one")], "expectations"),
        ([case(expected_output=None)], "expected_output"),
        ([case(id="1")], "id"),
    ],
)
def test_load_cases_rejects_malformed_cases(
    tmp_path: Path, cases: list[dict[str, object]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_cases(write_evals(tmp_path, cases))


def test_load_cases_requires_the_skill_name(tmp_path: Path) -> None:
    path = write_evals(tmp_path, [case()])
    path.write_text(json.dumps({"evals": [case()]}), encoding="utf-8")
    with pytest.raises(ValueError, match="skill_name"):
        load_cases(path)


def make_run(tmp_path: Path, deliverable: str | None) -> Path:
    run_dir = tmp_path / "iteration-1" / "data-gap" / "with_skill"
    (run_dir / "outputs").mkdir(parents=True)
    (run_dir.parent / "eval_metadata.json").write_text(
        json.dumps({"eval_id": 1, "eval_name": "data-gap"}), encoding="utf-8"
    )
    if deliverable is not None:
        (run_dir / "outputs" / "deliverable.md").write_text(
            deliverable, encoding="utf-8"
        )
    return run_dir


def read_grading(run_dir: Path) -> dict[str, object]:
    grading: dict[str, object] = json.loads(
        (run_dir / "grading.json").read_text(encoding="utf-8")
    )
    return grading


def test_main_writes_grading_with_summary(tmp_path: Path) -> None:
    evals = write_evals(tmp_path, [case()])
    run_dir = make_run(tmp_path, "The slope was 4.90 V and 7.3 V.")
    assert main([str(run_dir), "--evals", str(evals)]) == 0
    grading = read_grading(run_dir)
    assert grading["summary"] == {
        "passed": 1,
        "failed": 1,
        "total": 2,
        "pass_rate": 0.5,
    }


def test_main_keeps_judgement_entries_and_replaces_automatic_ones(
    tmp_path: Path,
) -> None:
    evals = write_evals(tmp_path, [case()])
    run_dir = make_run(tmp_path, "The slope was 4.90 V.")
    judged = {
        "text": "The slope is reported with its unit",
        "passed": True,
        "evidence": "x",
    }
    stale = {"text": f"{AUTO_PREFIX}old check", "passed": False, "evidence": "y"}
    (run_dir / "grading.json").write_text(
        json.dumps({"expectations": [judged, stale], "timing": {"total": 1}}),
        encoding="utf-8",
    )
    assert main([str(run_dir), "--evals", str(evals)]) == 0
    grading = read_grading(run_dir)
    texts = [entry["text"] for entry in grading["expectations"]]  # type: ignore[attr-defined]
    assert texts[0] == judged["text"]
    assert stale["text"] not in texts
    assert grading["timing"] == {"total": 1}
    assert grading["summary"] == {
        "passed": 3,
        "failed": 0,
        "total": 3,
        "pass_rate": 1.0,
    }


def test_main_fails_every_check_when_the_deliverable_is_missing(tmp_path: Path) -> None:
    evals = write_evals(tmp_path, [case()])
    run_dir = make_run(tmp_path, None)
    assert main([str(run_dir), "--evals", str(evals)]) == 0
    grading = read_grading(run_dir)
    assert grading["summary"] == {
        "passed": 0,
        "failed": 2,
        "total": 2,
        "pass_rate": 0.0,
    }


def test_main_refuses_a_corrupt_grading_file_and_leaves_it(tmp_path: Path) -> None:
    evals = write_evals(tmp_path, [case()])
    run_dir = make_run(tmp_path, "The slope was 4.90 V.")
    (run_dir / "grading.json").write_text("{not json", encoding="utf-8")
    assert main([str(run_dir), "--evals", str(evals)]) == 2
    assert (run_dir / "grading.json").read_text(encoding="utf-8") == "{not json"


def test_main_refuses_a_run_without_metadata(tmp_path: Path) -> None:
    evals = write_evals(tmp_path, [case()])
    run_dir = tmp_path / "loose"
    run_dir.mkdir()
    assert main([str(run_dir), "--evals", str(evals)]) == 2


def test_shipped_eval_set_loads_with_judgement_and_automatic_checks() -> None:
    cases = load_cases(DEFAULT_EVALS)
    assert len(cases) == 9
    for loaded in cases.values():
        assert loaded.expectations
        assert loaded.checks
