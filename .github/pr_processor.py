import os
import re

from github import Github
from github.GithubException import UnknownObjectException
from redminelib import Redmine

REDMINE_URL = "https://pulp.plan.io"
REDMINE_KEY = os.environ["REDMINE_API_KEY"]

GITHUB_TOKEN = os.environ["GITHUB_API_TOKEN"]
REPOSITORY = os.environ["REPOSITORY"]
PR_NUMBER = os.environ["PR_NUMBER"]

PR_STATUS = 3  # POST
KEYWORDS = ["fixes", "closes", "re", "ref"]

if not REDMINE_KEY or not GITHUB_TOKEN:
    print("Missing redmine and/or github api key.")
    exit(0)

redmine = Redmine(REDMINE_URL, key=REDMINE_KEY)
g = Github(GITHUB_TOKEN)
grepo = g.get_repo(REPOSITORY)
pr = grepo.get_pull(int(PR_NUMBER))

regex = r"(?:{keywords})[\s:]+#(\d+)".format(keywords=("|").join(KEYWORDS))
pattern = re.compile(regex)

issues = []
for commit in pr.get_commits():
    message = commit.commit.message
    issues.extend(pattern.findall(message))


# UPDATE THE ISSUE IN REDMINE

needs_cherry_pick = False

if not issues:
    comment = (
        "WARNING!!! This PR is not attached to an issue. In most cases this is not advisable. "
        "Please see [our PR docs](http://docs.pulpproject.org/contributing/git.html#commit-message)"
        " for more information about how to attach this PR to an issue."
    )
else:
    comment = ""
    for issue_num in issues:
        issue = redmine.issue.get(issue_num)

        if issue.tracker.name == "Issue":
            needs_cherry_pick = True

        if issue.status.id <= PR_STATUS:
            redmine.issue.update(issue_num, status_id=3, notes=f"PR: {pr.url}")
            comment += f"Attached issue: {issue.url}\n\n"
        else:
            comment += f"Warning: Issue [#{issue.id}]({issue.url}) is not at NEW/ASSIGNED/POST.\n\n"
            redmine.issue.update(issue_num, notes=f"PR: {pr.url}")

grepo.get_issue(pr.number).create_comment(comment)


# ADD LABELS

if needs_cherry_pick:
    try:
        label = grepo.get_label("Needs Cherry Pick")
    except UnknownObjectException:
        print("No cherry pick label found.")
        exit(0)

    labels = pr.labels + [label]
    grepo.get_issue(pr.number).edit(labels=[l.name for l in labels])
