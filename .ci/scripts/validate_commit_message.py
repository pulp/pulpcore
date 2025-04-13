# This file is managed by the plugin template.
# Do not edit.

import os
import re
import subprocess
import sys
import tomllib
import yaml
from pathlib import Path

from github import Github


def check_status(issue, repo, cherry_pick):
    gi = repo.get_issue(int(issue))
    if gi.pull_request:
        sys.exit(f"Error: issue #{issue} is a pull request.")
    if gi.closed_at and not cherry_pick:
        print("Make sure to use 'git cherry-pick -x' when backporting a change.")
        print(
            "If a backport of a change requires a significant amount of rewriting, "
            "consider creating a new issue."
        )
        sys.exit(f"Error: issue #{issue} is closed.")


def check_changelog(issue, CHANGELOG_EXTS):
    matches = list(Path("CHANGES").rglob(f"{issue}.*"))

    if len(matches) < 1:
        sys.exit(f"Could not find changelog entry in CHANGES/ for {issue}.")
    for match in matches:
        if match.suffix not in CHANGELOG_EXTS:
            sys.exit(f"Invalid extension for changelog entry '{match}'.")


def main() -> None:
    TEMPLATE_CONFIG = yaml.safe_load(Path("template_config.yml").read_text())
    GITHUB_ORG = TEMPLATE_CONFIG["github_org"]
    PLUGIN_NAME = TEMPLATE_CONFIG["plugin_name"]

    with Path("pyproject.toml").open("rb") as _fp:
        PYPROJECT_TOML = tomllib.load(_fp)
    KEYWORDS = ["fixes", "closes"]
    BLOCKING_REGEX = [
        r"^DRAFT",
        r"^WIP",
        r"^NOMERGE",
        r"^DO\s*NOT\s*MERGE",
        r"^EXPERIMENT",
        r"^FIXUP",
        r"^fixup!",  # This is created by 'git commit --fixup'
        r"Apply suggestions from code review",  # This usually comes from GitHub
    ]
    try:
        CHANGELOG_EXTS = [
            f".{item['directory']}" for item in PYPROJECT_TOML["tool"]["towncrier"]["type"]
        ]
    except KeyError:
        CHANGELOG_EXTS = [".feature", ".bugfix", ".doc", ".removal", ".misc"]
    NOISSUE_MARKER = "[noissue]"

    sha = sys.argv[1]
    message = subprocess.check_output(["git", "log", "--format=%B", "-n 1", sha]).decode("utf-8")

    if NOISSUE_MARKER in message:
        sys.exit(f"Do not add '{NOISSUE_MARKER}' in the commit message.")

    blocking_matches = [m for m in (re.match(pattern, message) for pattern in BLOCKING_REGEX) if m]
    if blocking_matches:
        print("Found these phrases in the commit message:")
        for m in blocking_matches:
            print(" - " + m.group(0))
        sys.exit("This PR is not ready for consumption.")

    g = Github(os.environ.get("GITHUB_TOKEN"))
    repo = g.get_repo(f"{GITHUB_ORG}/{PLUGIN_NAME}")

    print("Checking commit message for {sha}.".format(sha=sha[0:7]))

    # validate the issue attached to the commit
    issue_regex = r"(?:{keywords})[\s:]+#(\d+)".format(keywords="|".join(KEYWORDS))
    issues = re.findall(issue_regex, message, re.IGNORECASE)
    cherry_pick_regex = r"^\s*\(cherry picked from commit [0-9a-f]*\)\s*$"
    cherry_pick = re.search(cherry_pick_regex, message, re.MULTILINE)

    if issues:
        for issue in issues:
            check_status(issue, repo, cherry_pick)
            check_changelog(issue, CHANGELOG_EXTS)

    print("Commit message for {sha} passed.".format(sha=sha[0:7]))


if __name__ == "__main__":
    main()
