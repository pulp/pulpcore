#!/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# ]
# ///
import re
import sys
from pathlib import Path

import tomllib

EXCEPTIONS = [
    ".TEMPLATE.md",
    ".gitkeep",
    ".gitignore",
    "plugin_api",
    "pulp_file",
    "pulp_certguard",
]


def snippet_valid(path: Path, changelog_exts: list[str]) -> bool:
    return (path.name in EXCEPTIONS) or (
        path.suffix in changelog_exts
        and (path.stem.startswith("+") or re.fullmatch(r"\d*", path.stem))
    )


if __name__ == "__main__":
    with Path("pyproject.toml").open("rb") as fp:
        pyproject_toml = tomllib.load(fp)
    try:
        changelog_exts = [
            f".{item['directory']}" for item in pyproject_toml["tool"]["towncrier"]["type"]
        ]
    except KeyError:
        changelog_exts = [".feature", ".bugfix", ".doc", ".removal", ".misc"]
    matches = Path("CHANGES").rglob("*")
    invalid_snippets = ", ".join(f"'{s}'" for s in matches if not snippet_valid(s, changelog_exts))
    if invalid_snippets:
        sys.exit(f"LINT: Invalid changelog entries: {invalid_snippets}.")
