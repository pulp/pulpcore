import os
import subprocess
import uuid
from git import Repo
from github import Github
from github.GithubException import UnknownObjectException

PR_LABEL = "Needs Cherry Pick"
STABLE_BRANCH = os.environ["STABLE_BRANCH"]
REPOSITORY = os.environ["TRAVIS_REPO_SLUG"]
GITHUB_USER = os.environ["GITHUB_USER"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

# prepare our local repo to receive git cherry picks
repo = Repo(os.getcwd())
remote_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{REPOSITORY}.git"
remote = repo.create_remote("auth-origin", url=remote_url)
remote.fetch()
repo.git.checkout(STABLE_BRANCH)

g = Github(GITHUB_TOKEN)
grepo = g.get_repo(REPOSITORY)
(label,) = (l for l in grepo.get_labels() if l.name == PR_LABEL)
issues = grepo.get_issues(labels=[label], state="all")

cherrypicks = []

for issue in issues:
    try:
        pr = grepo.get_pull(issue.number)
    except UnknownObjectException:
        continue

    if not pr.merged:
        print(f"Pull request {pr.number} not merged. Skipping.")
        continue

    print(f"Attempting to cherry-pick commits for PR {pr.number}.")

    for commit in pr.get_commits():
        # looks like GitPython doesn't support cherry picks
        ret = subprocess.run(["git", "cherry-pick", "-x", commit.sha], stderr=subprocess.PIPE)

        if ret.returncode != 0:
            print(f"Failed to cherry-pick commit {commit.sha}: {ret.stderr.decode('ascii')}")
            exit(1)
        else:
            cherrypicks.append(issue)
            print(f"Cherry-picked commit {commit.sha}.")

# check if we cherry picked anything
if len(cherrypicks) == 0:
    print(f"No cherry picks detected.")
    exit(0)

# push our changes
print(f"Attempting push changes to {REPOSITORY}.")
cherry_pick_branch = f"cherry-picks-{uuid.uuid4()}"
remote.push(refspec=f"{STABLE_BRANCH}:{cherry_pick_branch}")
print(f"Pushed cherry picks to {cherry_pick_branch}.")

# create a pull request
body = f"Cherry picking #{(', #').join(str(cp.number) for cp in cherrypicks)}."
pr = grepo.create_pull(f"Cherry picks to {STABLE_BRANCH}", body, STABLE_BRANCH, cherry_pick_branch)
print(f"Created pull request {pr.html_url}.")

# remove the cherry pick label from our PRs
for cp in cherrypicks:
    labels = cp.labels
    labels.remove(label)
    cp.edit(labels=labels)
    print(f"Removed label '{PR_LABEL}' from PR #{cp.number}.")

print("Cherry picking complete.")
