import re
import os
import requests
from packaging.version import Version
from git import Repo

repo = Repo(os.getcwd())
heads = repo.git.ls_remote("--heads", "https://github.com/pulp/pulpcore.git").split("\n")
branches = [h.split("/")[-1] for h in heads if re.search(r"^([0-9]+)\.([0-9]+)$", h.split("/")[-1])]
branches.sort(key=lambda ver: Version(ver), reverse=True)


def get_changelog(branch):
    """
    Get changelog file for a given branch.

    """
    return requests.get(
        f"https://raw.githubusercontent.com/pulp/pulpcore/{branch}/CHANGES.rst"
    ).text


def get_changelog_releases(changelog):
    """
    Get all versions in changelog.

    """
    versions = re.findall(r"([0-9]+)\.([0-9]+)\.([0-9]+) \(", changelog)
    return {".".join(v) for v in versions}


def get_changelog_entry(changelog, version):
    """
    Get changelog entry for a given version.

    """
    entries = changelog.split(f"{version} (")[1].split("=====\n")
    header = f"{version} ({entries[0]}=====\n"
    text = "\n\n\n".join(entries[1].split("\n\n\n")[0:-1])
    return header + text + "\n\n\n"


main_changelog = get_changelog("main")
main_entries = get_changelog_releases(main_changelog)
entries_list = list(main_entries)
to_add = {}
for branch in branches:
    changelog = get_changelog(branch)
    entries = get_changelog_releases(changelog)
    for entry in entries.difference(main_entries):
        description = get_changelog_entry(changelog, entry)
        entries_list.append(entry)
        print(description)
        to_add[entry] = description

entries_list.sort(key=lambda ver: Version(ver), reverse=True)
for version in sorted(to_add, key=lambda ver: Version(ver)):
    next_version = entries_list[entries_list.index(version) + 1]
    new_changelog = main_changelog.split(f"{next_version} (")[0] + to_add[version]
    new_changelog = new_changelog + f"{next_version} ("
    new_changelog = new_changelog + main_changelog.split(f"{next_version} (")[1]
    main_changelog = new_changelog

with open("CHANGES.rst", "w") as f:
    f.write(main_changelog)

if to_add:
    repo.git.commit("-m", "Update Changelog\n\n[noissue]", "CHANGES.rst")
