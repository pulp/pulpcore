"""
Release script

$ python .travis/realease.py

Args:
    new_version - version to be released
    new_dev_version - dev version to be bumped after release
    current_pulpcore_version - lower bound of pulpcore requirement
    next_pulpcore_version - upper bound of pulpcore requirement

Example:
setup.py on plugin before script:
    version="2.0.dev"
    requirements = ["pulpcore>=3.4"]


$ python .travis/realease.py 2.0 2.1 4.0 4.1

setup.py on plugin after script:
    version="2.1.dev"
    requirements = ["pulpcore>=4.0,<4.1"]

"""

import os
import sys

from git import Repo

from pulpcore import __version__ as current_dev_version


release_path = os.path.dirname(os.path.abspath(__file__))
plugin_path = release_path
if ".travis" in release_path:
    plugin_path = os.path.dirname(release_path)

new_version = sys.argv[1]
new_dev_version = sys.argv[2]
if ".dev" not in new_dev_version:
    new_dev_version = f"{new_dev_version}.dev"

if "pulpcore" not in release_path:
    pulpcore_version = sys.argv[3]
    next_pulpcore_version = sys.argv[4]

current_version = current_dev_version.replace(".dev", "")

print("\n\nHave you checked the output of: $towncrier --version x.y.z --draft")
print(f"\n\nRepo path: {plugin_path}")
repo = Repo(plugin_path)
git = repo.git

git.checkout("HEAD", b=f"release_{new_version}")

# First commit: changelog
os.system(f"towncrier --yes --version {new_version}")
git.add(".")
git.commit("-m", f"Building changelog for {new_version}\n\n[noissue]")

# Second commit: release version
with open(f"{plugin_path}/setup.py", "rt") as setup_file:
    setup_lines = setup_file.readlines()

with open(f"{plugin_path}/setup.py", "wt") as setup_file:
    for line in setup_lines:
        if "version=" in line:
            line = line.replace(current_dev_version, new_version)
        if "pulpcore" in line and "entry_points" not in line and "pulpcore" not in release_path:
            sep = "'" if len(line.split('"')) == 1 else '"'
            for word in line.split(sep):
                if "pulpcore" in word:
                    pulpcore_word = word

            line = line.replace(
                pulpcore_word, f"pulpcore>={pulpcore_version},<{next_pulpcore_version}"
            )

        setup_file.write(line)

plugin_name = plugin_path.split("/")[-1]
with open(f"{plugin_path}/{plugin_name}/__init__.py", "rt") as init_file:
    init_lines = init_file.readlines()

with open(f"{plugin_path}/{plugin_name}/__init__.py", "wt") as init_file:
    for line in init_lines:
        if "__version__" in line:
            line = line.replace(current_dev_version, new_version)
        init_file.write(line)

git.add(".")
git.commit("-m", f"Releasing {new_version}\n\n[noissue]")

sha = repo.head.object.hexsha
short_sha = git.rev_parse(sha, short=7)

# Third commit: bump to .dev
with open(f"{plugin_path}/setup.py", "wt") as setup_file:
    for line in setup_lines:
        if "version=" in line:
            line = line.replace(current_dev_version, new_dev_version)
        if "pulpcore" in line and "entry_points" not in line and "pulpcore" not in release_path:
            sep = "'" if len(line.split('"')) == 1 else '"'
            for word in line.split(sep):
                if "pulpcore" in word:
                    pulpcore_word = word

            line = line.replace(pulpcore_word, f"pulpcore>={pulpcore_version}")

        setup_file.write(line)

with open(f"{plugin_path}/{plugin_name}/__init__.py", "wt") as init_file:
    for line in init_lines:
        if "__version__" in line:
            line = line.replace(current_dev_version, new_dev_version)
        init_file.write(line)

git.add(".")
git.commit("-m", f"Bump to {new_dev_version}\n\n[noissue]")

print(f"\n\nRelease commit == {short_sha}")
