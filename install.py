"""Install the writing skill for Claude Code and build the zip for claude.ai.

Usage:
    python install.py [--skills-dir DIR] [--dist DIR] [--source DIR]

Copies the skill to <skills-dir>/writing, replacing an earlier copy of this
skill, and writes <dist>/writing.zip for upload in claude.ai under Settings,
Capabilities, Skills. Refuses to replace a folder that holds anything else.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

SKILL_NAME = "writing"
REPOSITORY = Path(__file__).resolve().parent
SKIPPED = shutil.ignore_patterns("__pycache__", "*.pyc")


def declares_this_skill(skill_md: str) -> bool:
    return re.search(rf"^name:\s*{SKILL_NAME}\s*$", skill_md, re.MULTILINE) is not None


def _holds_this_skill(folder: Path) -> bool:
    skill_md = folder / "SKILL.md"
    return skill_md.is_file() and declares_this_skill(
        skill_md.read_text(encoding="utf-8")
    )


def install_skill(source: Path, skills_dir: Path) -> Path:
    """Copy `source` to `skills_dir/writing` and return that path.

    Raises FileNotFoundError if `source` is not this skill, and FileExistsError
    if the target exists and holds anything other than this skill.
    """
    if not _holds_this_skill(source):
        raise FileNotFoundError(
            f"{source} has no SKILL.md declaring name: {SKILL_NAME}"
        )
    target = skills_dir / SKILL_NAME
    if target.exists() and not _holds_this_skill(target):
        raise FileExistsError(
            f"{target} holds something other than the {SKILL_NAME} skill;"
            " move it and run again"
        )
    # Copy beside the target first, so a failed copy never leaves a
    # half-installed skill.
    staging = skills_dir / f".{SKILL_NAME}.installing"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging, ignore=SKIPPED)
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)
    return target


def build_zip(source: Path, dist: Path) -> Path:
    """Write `dist/writing.zip` with the skill folder at its root; return its path."""
    dist.mkdir(parents=True, exist_ok=True)
    archive = dist / f"{SKILL_NAME}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            ):
                bundle.write(
                    path, f"{SKILL_NAME}/{path.relative_to(source).as_posix()}"
                )
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=REPOSITORY / SKILL_NAME)
    parser.add_argument(
        "--skills-dir", type=Path, default=Path.home() / ".claude" / "skills"
    )
    parser.add_argument("--dist", type=Path, default=REPOSITORY / "dist")
    args = parser.parse_args(argv)

    try:
        target = install_skill(args.source, args.skills_dir)
    except (FileNotFoundError, FileExistsError) as err:
        print(f"not installed: {err}", file=sys.stderr)
        return 1
    archive = build_zip(args.source, args.dist)
    print(f"installed for Claude Code: {target}")
    print(f"upload to claude.ai: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
