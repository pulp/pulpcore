#!/usr/bin/env python3
"""
skip_tests.py - Check if only documentation files were changed in a git branch

Usage:
    ./skip_tests.py <git_root> <reference_branch>

Arguments:
    git_root: The root directory of the git project
    reference_branch: The branch to compare against

Returns:
    0: Skip
    1: NoSkip
    *: Error
"""

import sys
import os
import re
import git
import textwrap
import argparse

DOC_PATTERNS = [
    r"^docs/",
    r"\.md$",
    r"LICENSE.*",
    r"CHANGELOG.*",
    r"CHANGES.*",
    r"CONTRIBUTING.*",
]

# Exit codes
CODE_SKIP = 0
CODE_NO_SKIP = 1
CODE_ERROR = 2


def main() -> int:
    git_root, reference_branch = get_args()
    changed_files = get_changed_files(git_root, reference_branch)
    if not changed_files:
        return CODE_SKIP
    doc_files = [f for f in changed_files if is_doc_file(f)]
    not_doc_files = set(changed_files) - set(doc_files)
    print_changes(doc_files, not_doc_files)
    if not_doc_files:
        return CODE_NO_SKIP
    else:
        return CODE_SKIP


# Utils


def get_changed_files(git_root: str, reference_branch: str) -> list[str]:
    """Get list of files changed between current branch and reference branch."""
    repo = git.Repo(git_root)
    diff_index = repo.git.diff("--name-only", reference_branch).strip()
    if not diff_index:
        return []
    return [f.strip() for f in diff_index.split("\n") if f.strip()]


def is_doc_file(file_path: str) -> bool:
    """Check if a file is a documentation file."""
    for pattern in DOC_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def print_changes(doc_files: list[str], not_doc_files: list[str]) -> None:
    display_doc = "    \n".join(doc_files)
    print(f"doc_files({len(doc_files)})")
    if doc_files:
        display_doc = "\n".join(doc_files)
        print(textwrap.indent(display_doc, "    "))

    print(f"non_doc_files({len(not_doc_files)})")
    if not_doc_files:
        display_non_doc = "    \n".join(not_doc_files)
        print(textwrap.indent(display_non_doc, "    "))


def get_args() -> tuple[str, str]:
    """Parse command line arguments and validate them."""
    parser = argparse.ArgumentParser(description="Check if CI can skip tests for a git branch")
    parser.add_argument("git_root", help="The root directory of the git project")
    parser.add_argument("reference_branch", help="The branch to compare against")
    args = parser.parse_args()
    git_root = os.path.abspath(args.git_root)
    ref_branch = args.reference_branch

    if not os.path.exists(git_root):
        raise ValueError(f"Git root directory does not exist: {git_root}")
    if not os.path.isdir(git_root):
        raise ValueError(f"Git root is not a directory: {git_root}")
    try:
        git.Repo(git_root)
    except git.InvalidGitRepositoryError:
        raise ValueError(f"Directory is not a git repository: {git_root}")
    return git_root, ref_branch


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(e)
        sys.exit(CODE_ERROR)
