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


def blobs_match(commit1, commit2):
    """Compare the file blobs of two commits."""
    if len(commit1.files) != len(commit2.files):
        return False

    for cf in commit1.files:
        files = [f for f in commit2.files if f.sha == cf.sha and f.filename == cf.filename]
        if len(files) == 0:
            return False

    return True


def get_merged_commits(pr):
    """
    Find the merged commits for a PR.

    Github allows PRs to be merged with 3 different strategies: merge, rebase, and squashing. Github
    doesn't record how a PR was merged in the API so we need to examine the merge commit to
    determine how the pr was merged and then return the commits based on that.
    """
    merge_commit = pr.base.repo.get_commit(pr.merge_commit_sha)

    if len(merge_commit.parents) > 1:
        # PR was just merged and we can use the PR's commits
        return pr.get_commits()
    elif blobs_match(merge_commit, pr.get_commits().reversed[0]):
        # if the last PR commit is the same as the merge commit then the PR was rebased
        commits = []
        commit = merge_commit
        for _ in pr.get_commits():
            if len(commit.parents) > 1:
                print(f"Ran into problem attempting to cherry pick {commit.sha}.")
                exit(1)
            commits.append(commit)
            commit = commit.parents[0]
        commits.reverse()
        return commits
    else:
        # we have a squashed commit. we can just use the merge commit
        return [merge_commit]


print(f"Processing cherry picks for {REPOSITORY}.")

# prepare our local repo to receive git cherry picks
repo = Repo(os.getcwd())
remote_url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{REPOSITORY}.git"
remote = repo.create_remote("auth-origin", url=remote_url)
remote.fetch()
repo.git.checkout(STABLE_BRANCH)

g = Github(GITHUB_TOKEN)
grepo = g.get_repo(REPOSITORY)
(label,) = (l for l in grepo.get_labels() if l.name == PR_LABEL)
issues = grepo.get_issues(labels=[label], state="all", sort="updated", direction="asc")

cherrypicks = []

for issue in issues:
    try:
        pr = grepo.get_pull(issue.number)
    except UnknownObjectException:
        # this issue is not a PR. skip it.
        continue

    if not pr.merged:
        print(f"Pull request {pr.number} not merged. Skipping.")
        continue

    print(f"Attempting to cherry-pick commits for {pr.html_url}.")

    for commit in get_merged_commits(pr):
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
