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
# One frontmatter line, the value optionally quoted as YAML allows.
NAME_LINE = re.compile(rf"^name:[ \t]*([\"']?){SKILL_NAME}\1[ \t]*$", re.MULTILINE)


def is_shipped(path: Path) -> bool:
    """Whether a file under the skill folder belongs in an installed copy."""
    return "__pycache__" not in path.parts and path.suffix != ".pyc"


def _holds_this_skill(folder: Path) -> bool:
    skill_md = folder / "SKILL.md"
    return skill_md.is_file() and bool(
        NAME_LINE.search(skill_md.read_text(encoding="utf-8"))
    )


def _skip_unshipped(directory: str, names: list[str]) -> set[str]:
    return {name for name in names if not is_shipped(Path(directory, name))}


def install_skill(source: Path, skills_dir: Path) -> Path:
    """Copy `source` to `skills_dir/writing` and return that path.

    Raises FileNotFoundError if `source` is not this skill, and FileExistsError
    if the target is a link or holds anything other than this skill.
    """
    if not _holds_this_skill(source):
        raise FileNotFoundError(
            f"{source} has no SKILL.md declaring name: {SKILL_NAME}"
        )
    target = skills_dir / SKILL_NAME
    if target.is_symlink() or target.is_junction():
        raise FileExistsError(f"{target} is a link; remove it and run again")
    if target.exists() and not _holds_this_skill(target):
        raise FileExistsError(
            f"{target} holds something other than the {SKILL_NAME} skill;"
            " move it and run again"
        )
    # Build the new copy beside the target and swap by renaming, so a failure
    # at any step leaves either the old install or the new one, never a mix.
    staging = skills_dir / f".{SKILL_NAME}.installing"
    retired = skills_dir / f".{SKILL_NAME}.previous"
    for leftover in (staging, retired):
        if leftover.exists():
            shutil.rmtree(leftover)
    shutil.copytree(source, staging, ignore=_skip_unshipped)
    if target.exists():
        target.rename(retired)
    staging.rename(target)
    if retired.exists():
        shutil.rmtree(retired)
    return target


def build_zip(source: Path, dist: Path) -> Path:
    """Write `dist/writing.zip` with the skill folder at its root; return its path."""
    dist.mkdir(parents=True, exist_ok=True)
    archive = dist / f"{SKILL_NAME}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob("*")):
            if path.is_file() and is_shipped(path.relative_to(source)):
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

    # Every failure here is the filesystem refusing (a foreign or locked
    # folder, a file where a folder should be); none needs a traceback.
    try:
        target = install_skill(args.source, args.skills_dir)
        archive = build_zip(args.source, args.dist)
    except OSError as err:
        # Windows renders err.filename with doubled backslashes inside str(err).
        detail = f"{err.strerror}: {err.filename}" if err.filename else str(err)
        print(f"not installed: {detail}", file=sys.stderr)
        return 1
    print(f"installed for Claude Code: {target}")
    print(f"upload to claude.ai: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
