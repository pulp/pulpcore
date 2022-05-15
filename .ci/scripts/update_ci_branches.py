import os
import re
import sys
import requests
from packaging.version import Version
from git import Repo

try:
    initial_branch = sys.argv[1]
except IndexError:
    initial_branch = None

repo = Repo(os.getcwd())
heads = repo.git.ls_remote("--heads", "https://github.com/pulp/pulpcore.git").split("\n")
branches = [h.split("/")[-1] for h in heads if re.search(r"^([0-9]+)\.([0-9]+)$", h.split("/")[-1])]
branches.sort(key=lambda ver: Version(ver))

headers = {
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "Accept": "application/vnd.github.v3+json",
}

if not initial_branch or initial_branch not in branches:
    exit("Initial branch not found")
else:
    starting = branches.index(initial_branch)

github_api = "https://api.github.com"
workflow_path = "/actions/workflows/update_ci.yml/dispatches"
url = f"{github_api}/repos/pulp/pulpcore{workflow_path}"

for branch in branches[starting:]:
    print(f"Updating {branch}")
    requests.post(url, headers=headers, json={"ref": branch})
