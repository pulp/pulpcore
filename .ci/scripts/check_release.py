#!/usr/bin/env python
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "gitpython>=3.1.46,<3.2.0",
#     "packaging>=26.0,<26.1",
#     "pyyaml>=6.0.3,<6.1.0",
# ]
# ///

import argparse
import re
import os
import tomllib
from pathlib import Path

import yaml
from packaging.version import Version
from git import Repo

RELEASE_BRANCH_REGEX = r"^([0-9]+)\.([0-9]+)$"
Y_CHANGELOG_EXTS = [".feature"]
Z_CHANGELOG_EXTS = [".bugfix", ".misc"]


def options():
    """Check which branches need a release."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--branches",
        default="supported",
        help="A comma separated list of branches to check for releases. Can also use keyword: "
        "'supported'. Defaults to 'supported', see `supported_release_branches` in "
        "`plugin_template.yml`.",
    )
    parser.add_argument(
        "--no-fetch",
        default=False,
        action="store_true",
        help="Don't fetch remote. Run faster at the expense of maybe being outdated.",
    )
    return parser.parse_args()


def template_config():
    # Assume this script lies in .ci/scripts
    path = Path(__file__).absolute().parent.parent.parent / "template_config.yml"
    return yaml.safe_load(path.read_text())


def current_version(repo, commitish):
    try:
        pyproject_toml = tomllib.loads(repo.git.show(f"{commitish}:pyproject.toml"))
        try:
            current_version = pyproject_toml["project"]["version"]
        except Exception:
            current_version = pyproject_toml["tool"]["bumpversion"]["current_version"]
    except Exception:
        current_version = repo.git.grep(
            "current_version", commitish, "--", ".bumpversion.cfg"
        ).split("=")[-1]
    return Version(current_version)


def check_pyproject_dependencies(repo, from_commit, to_commit):
    try:
        new_pyproject = tomllib.loads(repo.git.show(f"{to_commit}:pyproject.toml"))
        try:
            new_dependencies = set(new_pyproject["project"]["dependencies"])
        except KeyError:
            # New branch does not declare dependencies in pyproject.toml.
            # Assume no release needed for this reason.
            return []
        old_pyproject = tomllib.loads(repo.git.show(f"{from_commit}:pyproject.toml"))
        old_dependencies = set(old_pyproject["project"]["dependencies"])
        if old_dependencies != new_dependencies:
            return ["dependencies"]
        else:
            return []
    except Exception as e:
        print(f"WARNING: Comparing the dependencies in pyproject.toml failed. ({e})")
        # Gathering more details failed.
        return ["pyproject.toml changed somehow (PLEASE check if dependencies are affected)."]


def main(options, template_config):
    DEFAULT_BRANCH = template_config["plugin_default_branch"]

    repo = Repo()

    upstream_default_branch = next(
        (branch for branch in repo.branches if branch.name == DEFAULT_BRANCH)
    ).tracking_branch()
    remote = upstream_default_branch.remote_name
    if not options.no_fetch:
        repo.remote(remote).fetch()

    # Warning: This will not work if branch names contain "/" but we don't really care here.
    heads = [h.split("/")[-1] for h in repo.git.branch("--remote").split("\n")]
    available_branches = [h for h in heads if re.search(RELEASE_BRANCH_REGEX, h)]
    available_branches.sort(key=lambda ver: Version(ver))
    available_branches.append(DEFAULT_BRANCH)

    branches = options.branches
    if branches == "supported":
        tc = yaml.safe_load(repo.git.show(f"{upstream_default_branch}:template_config.yml"))
        branches = set(tc["supported_release_branches"])
        latest_release_branch = tc["latest_release_branch"]
        if latest_release_branch is not None:
            branches.add(latest_release_branch)
        branches.add(DEFAULT_BRANCH)
    else:
        branches = set(branches.split(","))

    if diff := branches - set(available_branches):
        print(f"Supplied branches contains non-existent branches! {diff}")
        exit(1)

    print(f"Checking for releases on branches: {branches}")

    releases = []
    for branch in branches:
        if branch != DEFAULT_BRANCH:
            # Check if a Z release is needed
            reasons = []
            changes = repo.git.ls_tree("-r", "--name-only", f"{remote}/{branch}", "CHANGES/")
            z_changelog = False
            for change in changes.split("\n"):
                # Check each changelog file to make sure everything checks out
                _, ext = os.path.splitext(change)
                if ext in Y_CHANGELOG_EXTS:
                    print(
                        f"Warning: A non-backported changelog ({change}) is present in the "
                        f"{branch} release branch!"
                    )
                elif ext in Z_CHANGELOG_EXTS:
                    z_changelog = True
            if z_changelog:
                reasons.append("Backports")

            last_tag = repo.git.describe("--tags", "--abbrev=0", f"{remote}/{branch}")
            req_txt_diff = repo.git.diff(
                f"{last_tag}", f"{remote}/{branch}", "--name-only", "--", "requirements.txt"
            )
            if req_txt_diff:
                reasons.append("requirements.txt")
            pyproject_diff = repo.git.diff(
                f"{last_tag}", f"{remote}/{branch}", "--name-only", "--", "pyproject.toml"
            )
            if pyproject_diff:
                reasons.extend(check_pyproject_dependencies(repo, last_tag, f"{remote}/{branch}"))

            if reasons:
                curr_version = Version(last_tag)
                assert curr_version.base_version.startswith(
                    branch
                ), "Current-version has to belong to the current branch!"
                next_version = Version(f"{branch}.{curr_version.micro + 1}")
                print(
                    f"A Z-release is needed for {branch}, "
                    f"Prev: {last_tag}, "
                    f"Next: {next_version.base_version}, "
                    f"Reason: {','.join(reasons)}"
                )
                releases.append(next_version)
        else:
            # Check if a Y release is needed
            changes = repo.git.ls_tree("-r", "--name-only", DEFAULT_BRANCH, "CHANGES/")
            for change in changes.split("\n"):
                _, ext = os.path.splitext(change)
                if ext in Y_CHANGELOG_EXTS:
                    # We don't put Y release bumps in the commit message, check file instead.
                    # The 'current_version' is always the dev of the next version to release.
                    next_version = current_version(repo, DEFAULT_BRANCH).base_version
                    print(f"A new Y-release is needed! New Version: {next_version}")
                    releases.append(next_version)
                    break

    if len(releases) == 0:
        print("No new releases to perform.")


if __name__ == "__main__":
    main(options(), template_config())
