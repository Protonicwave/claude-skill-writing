import re
import sys
import zipfile
from pathlib import Path

import pytest

from install import SKILL_NAME, build_zip, install_skill, main


def make_skill(root: Path) -> Path:
    source = root / "source" / SKILL_NAME
    (source / "registers").mkdir(parents=True)
    (source / "SKILL.md").write_text(
        f"---\nname: {SKILL_NAME}\n---\nBody\n", encoding="utf-8"
    )
    (source / "registers" / "report.md").write_text("Report\n", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "check.cpython-312.pyc").write_bytes(b"\x00")
    return source


def tree(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }


def test_installs_into_an_empty_skills_directory(tmp_path: Path) -> None:
    source = make_skill(tmp_path)
    skills = tmp_path / "skills"

    target = install_skill(source, skills)

    assert target == skills / SKILL_NAME
    assert tree(target) == {"SKILL.md", "registers/report.md"}


def test_reinstall_replaces_the_previous_copy(tmp_path: Path) -> None:
    source = make_skill(tmp_path)
    skills = tmp_path / "skills"
    install_skill(source, skills)
    (skills / SKILL_NAME / "stale.md").write_text("old\n", encoding="utf-8")

    install_skill(source, skills)

    assert "stale.md" not in tree(skills / SKILL_NAME)


@pytest.mark.parametrize("existing_skill_md", ["---\nname: other\n---\n", None])
def test_refuses_to_overwrite_a_different_skill(
    tmp_path: Path, existing_skill_md: str | None
) -> None:
    source = make_skill(tmp_path)
    foreign = tmp_path / "skills" / SKILL_NAME
    foreign.mkdir(parents=True)
    (foreign / "notes.md").write_text("mine\n", encoding="utf-8")
    if existing_skill_md is not None:
        (foreign / "SKILL.md").write_text(existing_skill_md, encoding="utf-8")

    with pytest.raises(FileExistsError, match=re.escape(str(foreign))):
        install_skill(source, tmp_path / "skills")

    assert (foreign / "notes.md").read_text(encoding="utf-8") == "mine\n"


def test_zip_holds_the_skill_folder_at_its_root(tmp_path: Path) -> None:
    source = make_skill(tmp_path)

    archive = build_zip(source, tmp_path / "dist")

    with zipfile.ZipFile(archive) as opened:
        assert set(opened.namelist()) == {
            "writing/SKILL.md",
            "writing/registers/report.md",
        }


def test_main_reports_a_refusal_with_exit_code_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = make_skill(tmp_path)
    foreign = tmp_path / "skills" / SKILL_NAME
    foreign.mkdir(parents=True)

    code = main(
        [
            "--source",
            str(source),
            "--skills-dir",
            str(tmp_path / "skills"),
            "--dist",
            str(tmp_path / "dist"),
        ]
    )

    assert code == 1
    assert str(foreign) in capsys.readouterr().err
    assert not (tmp_path / "dist").exists()


def test_main_installs_and_builds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = make_skill(tmp_path)

    code = main(
        [
            "--source",
            str(source),
            "--skills-dir",
            str(tmp_path / "skills"),
            "--dist",
            str(tmp_path / "dist"),
        ]
    )

    assert code == 0
    assert (tmp_path / "skills" / SKILL_NAME / "SKILL.md").is_file()
    assert (tmp_path / "dist" / "writing.zip").is_file()
    assert "writing.zip" in capsys.readouterr().out


def test_main_refuses_a_source_that_is_not_the_skill(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    code = main(
        [
            "--source",
            str(empty),
            "--skills-dir",
            str(tmp_path / "skills"),
            "--dist",
            str(tmp_path / "dist"),
        ]
    )

    assert code == 1
    assert not (tmp_path / "skills").exists()


@pytest.mark.parametrize(
    ("skill_md", "accepted"),
    [
        ('---\nname: "writing"\n---\n', True),
        ("---\nname: 'writing'\n---\n", True),
        ("---\nname:\nwriting\n---\n", False),
    ],
)
def test_source_name_is_read_as_one_frontmatter_line(
    tmp_path: Path, skill_md: str, accepted: bool
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text(skill_md, encoding="utf-8")

    if accepted:
        install_skill(source, tmp_path / "skills")
    else:
        with pytest.raises(FileNotFoundError):
            install_skill(source, tmp_path / "skills")


def test_refuses_a_target_that_is_a_link(tmp_path: Path) -> None:
    source = make_skill(tmp_path)
    checkout = make_skill(tmp_path / "checkout")
    skills = tmp_path / "skills"
    skills.mkdir()
    try:
        (skills / SKILL_NAME).symlink_to(checkout, target_is_directory=True)
    except OSError:
        # Windows refuses symlinks without a privilege; a junction is the
        # link an unprivileged Windows user would make instead.
        if sys.platform != "win32":
            raise
        import _winapi  # Windows-only module, imported where used

        _winapi.CreateJunction(str(checkout), str(skills / SKILL_NAME))

    with pytest.raises(FileExistsError, match="link"):
        install_skill(source, skills)

    assert (checkout / "SKILL.md").is_file()


def test_main_reports_a_filesystem_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = make_skill(tmp_path)
    blocked = tmp_path / "dist"
    blocked.write_text("a file where the folder should be\n", encoding="utf-8")

    code = main(
        [
            "--source",
            str(source),
            "--skills-dir",
            str(tmp_path / "skills"),
            "--dist",
            str(blocked),
        ]
    )

    assert code == 1
    assert str(blocked) in capsys.readouterr().err
