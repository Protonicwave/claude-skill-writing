import re
from pathlib import Path

import pytest
from check import Format, Severity, find_issues

SKILL_DIR = Path(__file__).resolve().parent.parent / "writing"
SKILL_TEXT = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
# Limits from the skill format: claude.ai rejects a skill that exceeds them.
MAX_NAME_CHARACTERS = 64
MAX_DESCRIPTION_CHARACTERS = 1024


def frontmatter() -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", SKILL_TEXT, re.DOTALL)
    assert match, "SKILL.md must open with a frontmatter block"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def referenced_paths() -> set[str]:
    return set(re.findall(r"`((?:registers/|scripts/)?[\w-]+\.(?:md|py))`", SKILL_TEXT))


def shipped_files() -> set[str]:
    return {
        path.relative_to(SKILL_DIR).as_posix()
        for path in SKILL_DIR.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.name != "SKILL.md"
    }


def test_frontmatter_has_valid_name_and_description() -> None:
    fields = frontmatter()
    assert fields["name"] == "writing"
    assert len(fields["name"]) <= MAX_NAME_CHARACTERS
    assert 0 < len(fields["description"]) <= MAX_DESCRIPTION_CHARACTERS
    assert "<" not in fields["description"]
    assert ">" not in fields["description"]


def test_every_file_skill_md_names_exists() -> None:
    missing = {path for path in referenced_paths() if not (SKILL_DIR / path).is_file()}
    assert missing == set()


def test_every_shipped_file_is_named_in_skill_md() -> None:
    assert shipped_files() - referenced_paths() == set()


@pytest.mark.parametrize(
    "path",
    sorted(SKILL_DIR.rglob("*.md")),
    ids=lambda path: path.relative_to(SKILL_DIR).as_posix(),
)
def test_skill_files_pass_the_checker(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    errors = [
        issue
        for issue in find_issues(text, Format.MARKDOWN)
        if issue.severity is Severity.ERROR
    ]
    assert errors == []
