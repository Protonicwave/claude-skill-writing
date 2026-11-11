import time
from pathlib import Path

import pytest
from check import (
    Format,
    Issue,
    Severity,
    find_issues,
    main,
    outline,
    split_sentences,
)

EM_DASH = "\u2014"
EN_DASH = "\u2013"


def rules(text: str, fmt: Format = Format.PLAIN) -> set[str]:
    return {issue.rule for issue in find_issues(text, fmt)}


def uniform_paragraph(sentences: int) -> str:
    return " ".join(
        "The laser output was measured at each pump power." for _ in range(sentences)
    )


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (f"The fit failed{EM_DASH}badly.", "dash"),
        (f"The fit failed {EN_DASH} badly.", "dash"),
        ("The fit failed - badly.", "dash"),
        ("Rocket emoji \U0001f680 here.", "emoji"),
        ("I hope this helps with the report.", "chatbot"),
        ("As an AI language model, I cannot measure.", "chatbot"),
    ],
)
def test_error_rules_flag_their_pattern(text: str, rule: str) -> None:
    issues = [i for i in find_issues(text, Format.PLAIN) if i.rule == rule]
    assert issues
    assert all(i.severity is Severity.ERROR for i in issues)


@pytest.mark.parametrize(
    "text",
    [
        f"Pages 10{EN_DASH}20 cover the derivation.",
        f"The Hartree{EN_DASH}Fock method converged.",
        "A well-known result holds.",
        "The difference 5 - 3 is two.",
        "Let me know if the figures print badly.",
    ],
)
def test_error_rules_spare_legitimate_text(text: str) -> None:
    assert not [
        i for i in find_issues(text, Format.PLAIN) if i.severity is Severity.ERROR
    ]


def test_markdown_list_marker_is_not_a_dash() -> None:
    assert "dash" not in rules("- first item\n- second item", Format.MARKDOWN)


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("This study delves into spin glasses.", "vocabulary"),
        ("The result underscores the method.", "vocabulary"),
        ("A pivotal parameter sets the scale.", "vocabulary"),
        ("Optics offers a promising avenue for computing.", "vocabulary"),
        ("Optical machines have emerged as a platform.", "stock-phrase"),
        ("The gain rose, highlighting the role of noise.", "significance-clause"),
        ("The fit converged, ensuring a stable estimate.", "significance-clause"),
        ("It is important to note that the gain saturates.", "stock-phrase"),
        ("Temperature plays a crucial role in annealing.", "stock-phrase"),
        ("The mirror serves as a reference arm.", "stock-phrase"),
        ("It is not just faster, but also cheaper.", "stock-phrase"),
        ("In conclusion, the gain saturates.", "stock-phrase"),
        ("Additionally, the gain saturates.", "connective-opener"),
        ("The gain rose. Moreover, the noise fell.", "connective-opener"),
        ("The anneal may potentially improve the result.", "hedge-stack"),
        ("We optimized the pump power.", "us-spelling"),
        ("The color of the beam changed.", "us-spelling"),
        ("The beam hit the center of the camera.", "us-spelling"),
        ("The gain saturates [UNVERIFIED].", "unresolved-marker"),
        ("The gain saturates [CITATION NEEDED: saturation].", "unresolved-marker"),
        ("The gain saturates [CLAIM NOT CHECKED: paywalled].", "unresolved-marker"),
        ("The threshold was [DATA NEEDED: threshold power] W.", "unresolved-marker"),
    ],
)
def test_warning_rules_flag_their_pattern(text: str, rule: str) -> None:
    issues = [i for i in find_issues(text, Format.PLAIN) if i.rule == rule]
    assert issues
    assert all(i.severity is Severity.WARNING for i in issues)


@pytest.mark.parametrize(
    "text",
    [
        "The potential energy has two minima.",
        "The estimator is robust to outliers.",
        "The complex amplitude has a phase.",
        "The beam size was fixed by the aperture.",
        "We won a prize for the analysis.",
        "The camera recorded the intensity, and the code fitted it.",
        "In addition to the camera, a photodiode recorded the signal.",
        "The anneal may improve the result.",
        "We optimised the pump power and normalised the signal.",
        "The colour of the beam marked the centre of the camera.",
    ],
)
def test_warning_rules_spare_near_misses(text: str) -> None:
    assert rules(text) == set()


def test_bold_in_markdown_prose_is_flagged() -> None:
    assert "bold-in-prose" in rules("The **gain** saturates.", Format.MARKDOWN)


def test_bold_is_not_checked_in_plain_text() -> None:
    assert "bold-in-prose" not in rules("The **gain** saturates.", Format.PLAIN)


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("The gain rose. The noise fell.", 2),
        ("See Fig. 3 and Eq. 2 for details. The gain rose.", 2),
        ("Smith et al. measured it. The gain rose.", 2),
        ("The gain was 3.5 dB at 1.2 W. The noise fell.", 2),
        ("This follows R. P. Feynman closely. The gain rose.", 2),
        ("Noise, e.g. shot noise, i.e. Poisson noise, dominates. The gain rose.", 2),
        ("Did it converge? Yes! It did.", 3),
        ("", 0),
    ],
)
def test_sentence_splitter(text: str, count: int) -> None:
    assert len(split_sentences(text)) == count


def test_uniform_paragraph_gets_rhythm_warning() -> None:
    assert "rhythm" in rules(uniform_paragraph(6))


def test_varied_paragraph_has_no_rhythm_warning() -> None:
    text = (
        "The laser was set to 1.2 W. "
        "We then swept the pump power from 0.1 W to 2.0 W in twenty steps, "
        "recording the camera image and the photodiode signal at each step so that "
        "the two measurements could be compared afterwards. "
        "Nothing changed. "
        "Only above 1.6 W did the intensity pattern begin to break into the "
        "two-lobed shape the model predicts. "
        "That threshold matters. "
        "It sets the lowest pump power at which the machine can represent a "
        "frustrated spin configuration at all."
    )
    assert "rhythm" not in rules(text)


def test_short_paragraph_is_not_judged_for_rhythm() -> None:
    assert "rhythm" not in rules(uniform_paragraph(4))


def test_uniform_document_gets_document_rhythm_warning() -> None:
    paragraphs = "\n\n".join(uniform_paragraph(4) for _ in range(5))
    assert "document-rhythm" in rules(paragraphs)


def test_latex_em_and_spaced_en_dashes_are_flagged() -> None:
    assert "dash" in rules("The fit failed---badly.", Format.LATEX)
    assert "dash" in rules("The fit failed -- badly.", Format.LATEX)


def test_latex_ranges_and_names_pass() -> None:
    assert rules("Pages 10--20 use the Hartree--Fock method.", Format.LATEX) == set()


def test_latex_comments_and_maths_are_ignored() -> None:
    text = (
        "% the gain plays a crucial role here\n"
        "The energy $E = -\\sum_{ij} J_{ij} s_i s_j$ is minimised.\n"
        "\\begin{equation}\n"
        "  H = - J \\cdot s . \\text{delves}\n"
        "\\end{equation}\n"
        "The result is in \\cite{leonetti2021} and Fig.~\\ref{fig:gain}.\n"
    )
    assert rules(text, Format.LATEX) == set()


def test_latex_escaped_percent_is_kept() -> None:
    assert "vocabulary" in rules("A 5\\% change, a pivotal one.", Format.LATEX)


def test_markdown_code_is_ignored() -> None:
    text = "Run `check --delves`.\n\n```\nx = a - b  # crucial\n```\n"
    assert rules(text, Format.MARKDOWN) == set()


def test_issue_reports_the_line_it_is_on() -> None:
    issues = find_issues("The gain rose.\n\nThis study delves into it.", Format.PLAIN)
    assert issues == [
        Issue(
            3,
            "vocabulary",
            Severity.WARNING,
            "decorative word 'delves': say the specific thing instead",
        )
    ]


def test_latex_line_numbers_survive_stripping() -> None:
    text = "% comment\n$x$\n\\begin{equation}\na\n\\end{equation}\nA pivotal step."
    assert [i.line for i in find_issues(text, Format.LATEX)] == [6]


@pytest.mark.parametrize("text", ["", "   \n\n  \n"])
def test_empty_input_has_no_issues(text: str) -> None:
    assert find_issues(text, Format.PLAIN) == []


# Short passages from writers admired for clarity, all published before 2022.
# Each must pass with no errors; warnings here would mean the rules punish good prose.
HUMAN_PASSAGES = [
    (
        "The fundamental problem of communication is that of reproducing at one point "
        "either exactly or approximately a message selected at another point. "
        "Frequently the messages have meaning; that is they refer to or are correlated "
        "according to some system with certain physical or conceptual entities. "
        "These semantic aspects of communication are irrelevant to the engineering "
        "problem."
    ),
    (
        "I propose to consider the question, \u201cCan machines think?\u201d "
        "This should begin with definitions of the meaning of the terms "
        "\u201cmachine\u201d and \u201cthink.\u201d"
    ),
    (
        "Let me start not logically, but psychologically. I find that the major "
        "objection is that people think great science is done by luck. It's all a "
        "matter of luck. Well, consider Einstein. Note how many different things he "
        "did that were good. Was it all luck? Wasn't it a little too repetitive?"
    ),
]


@pytest.mark.parametrize("text", HUMAN_PASSAGES)
def test_human_passages_raise_nothing(text: str) -> None:
    assert find_issues(text, Format.PLAIN) == []


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text("The gain rose.", encoding="utf-8")
    dirty = tmp_path / "dirty.md"
    dirty.write_text(f"The gain rose{EM_DASH}fast.", encoding="utf-8")
    warned = tmp_path / "warned.md"
    warned.write_text("This study delves into it.", encoding="utf-8")

    assert main([str(clean)]) == 0
    assert main([str(warned)]) == 0
    assert main([str(dirty)]) == 1
    assert "dirty.md:1: error [dash]" in capsys.readouterr().out


def test_cli_missing_file_names_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "absent.tex"
    assert main([str(missing)]) == 2
    assert str(missing) in capsys.readouterr().err


def test_cli_reads_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("A pivotal step."))
    assert main(["-"]) == 0
    assert "<stdin>:1: warning [vocabulary]" in capsys.readouterr().out


def test_cli_format_flag_overrides_extension(tmp_path: Path) -> None:
    draft = tmp_path / "draft.txt"
    draft.write_text("The fit failed---badly.", encoding="utf-8")
    assert main([str(draft)]) == 0
    assert main([str(draft), "--format", "latex"]) == 1


@pytest.mark.parametrize(
    ("text", "fmt"),
    [
        ("The gap is $E - V$ at the edge.", Format.MARKDOWN),
        ("The force is m a - k x here.", Format.PLAIN),
        ("\\begin{alignat}{2}\nx &= a - b\n\\end{alignat}", Format.LATEX),
        ("\\begin{flalign}\nx &= a - b\n\\end{flalign}", Format.LATEX),
        ("where $E\n- V$ is the gap.", Format.LATEX),
        ("As an AI researcher, I study alignment.", Format.PLAIN),
        ("GPT-2 was trained as a language model on WebText.", Format.PLAIN),
        ("The model has a knowledge cutoff of 2023.", Format.PLAIN),
    ],
)
def test_legitimate_physics_and_computing_prose_has_no_errors(
    text: str, fmt: Format
) -> None:
    assert not [i for i in find_issues(text, fmt) if i.severity is Severity.ERROR]


def test_latex_line_break_with_spacing_does_not_hide_prose() -> None:
    text = f"First line\\\\[6pt]\nSecond line{EM_DASH}with a dash.\n\n\\[ x = 1 \\]"
    assert "dash" in rules(text, Format.LATEX)


def test_latex_heading_label_is_not_prose() -> None:
    assert rules("\\section{Results}\\label{sec:fiber}", Format.LATEX) == set()


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("The polarizability rose.", "us-spelling"),
        ("An organizational change.", "us-spelling"),
        ("The vapor pressure fell.", "us-spelling"),
        ("A favorable result.", "us-spelling"),
        ("A colorful plot.", "us-spelling"),
        ("Done \u2714 and fast \u26a1.", "emoji"),
        ("Made in \U0001f1ec\U0001f1e7.", "emoji"),
        ("The gain saturates [citation needed].", "unresolved-marker"),
    ],
)
def test_review_false_negatives_are_caught(text: str, rule: str) -> None:
    assert rule in rules(text)


@pytest.mark.parametrize(
    ("text", "fmt"),
    [
        ("The dose was 2 gray.", Format.PLAIN),
        ("An outsize load.", Format.PLAIN),
        ("The assizes met.", Format.PLAIN),
        ("They stand as independents.", Format.PLAIN),
        ("See [the guide](https://example.com/color-guide).", Format.MARKDOWN),
        ("See https://example.com/color-guide for details.", Format.PLAIN),
    ],
)
def test_review_false_positives_are_spared(text: str, fmt: Format) -> None:
    assert rules(text, fmt) == set()


def test_one_phrase_gets_one_issue() -> None:
    issues = find_issues("Temperature plays a crucial role in annealing.", Format.PLAIN)
    assert [i.rule for i in issues] == ["stock-phrase"]


def test_long_paragraph_is_checked_in_linear_time() -> None:
    start = time.perf_counter()
    find_issues("color\n" * 12000, Format.PLAIN)
    assert time.perf_counter() - start < 2.0


def test_repeated_latex_line_breaks_are_checked_quickly() -> None:
    start = time.perf_counter()
    find_issues("\\\\[2pt] word " * 16000, Format.LATEX)
    assert time.perf_counter() - start < 2.0


OUTLINED_DRAFT = (
    "# Method\n"
    "\n"
    "We swept the pump power. The camera recorded each step.\n"
    "\n"
    "Above 1.6 W the pattern split\n"
    "into two lobes. That was the threshold.\n"
    "\n"
    "- one item\n"
)


def test_outline_gives_each_body_paragraph_first_sentence_with_its_line() -> None:
    assert outline(OUTLINED_DRAFT, Format.MARKDOWN) == [
        (3, "We swept the pump power."),
        (5, "Above 1.6 W the pattern split into two lobes."),
        (8, "one item"),
    ]


@pytest.mark.parametrize("text", ["", "# Only a heading\n"])
def test_outline_of_a_draft_without_body_is_empty(text: str) -> None:
    assert outline(text, Format.MARKDOWN) == []


def test_cli_outline_prints_sentences_and_runs_no_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = tmp_path / "draft.md"
    draft.write_text(f"The fit failed{EM_DASH}badly. It was redone.", encoding="utf-8")
    assert main([str(draft), "--outline"]) == 0
    assert capsys.readouterr().out == f"{draft}:1: The fit failed{EM_DASH}badly.\n"


def test_cli_outline_of_unreadable_draft_exits_2(tmp_path: Path) -> None:
    assert main([str(tmp_path / "absent.md"), "--outline"]) == 2
