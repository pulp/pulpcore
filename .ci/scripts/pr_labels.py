#!/bin/env python3

# This script is running with elevated privileges from the main branch against pull requests.

import re
import sys
import tomllib
from pathlib import Path

from git import Repo


def main():
    assert len(sys.argv) == 3

    with open("pyproject.toml", "rb") as fp:
        PYPROJECT_TOML = tomllib.load(fp)
    BLOCKING_REGEX = re.compile(r"DRAFT|WIP|NO\s*MERGE|DO\s*NOT\s*MERGE|EXPERIMENT")
    ISSUE_REGEX = re.compile(r"(?:fixes|closes)[\s:]+#(\d+)")
    CHERRY_PICK_REGEX = re.compile(r"^\s*\(cherry picked from commit [0-9a-f]*\)\s*$")
    CHANGELOG_EXTS = [
        f".{item['directory']}" for item in PYPROJECT_TOML["tool"]["towncrier"]["type"]
    ]

    repo = Repo(".")

    base_commit = repo.commit(sys.argv[1])
    head_commit = repo.commit(sys.argv[2])

    pr_commits = list(repo.iter_commits(f"{base_commit}..{head_commit}"))

    labels = {
        "multi-commit": len(pr_commits) > 1,
        "cherry-pick": False,
        "no-issue": False,
        "no-changelog": False,
        "wip": False,
    }
    for commit in pr_commits:
        labels["wip"] |= BLOCKING_REGEX.search(commit.summary) is not None
        no_issue = ISSUE_REGEX.search(commit.message, re.IGNORECASE) is None
        labels["no-issue"] |= no_issue
        cherry_pick = CHERRY_PICK_REGEX.search(commit.message) is not None
        labels["cherry-pick"] |= cherry_pick
        changelog_snippets = [
            k
            for k in commit.stats.files
            if k.startswith("CHANGES/") and Path(k).suffix in CHANGELOG_EXTS
        ]
        labels["no-changelog"] |= not changelog_snippets

    print("ADD_LABELS=" + ",".join((k for k, v in labels.items() if v)))
    print("REMOVE_LABELS=" + ",".join((k for k, v in labels.items() if not v)))


if __name__ == "__main__":
    main()
