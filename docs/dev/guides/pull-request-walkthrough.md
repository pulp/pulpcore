# Pull Request Walkthrough

Changes to pulpcore are submitted via
[GitHub Pull Requests (PR)](https://help.github.com/articles/about-pull-requests/) to the
[pulp git repository](https://github.com/pulp/pulpcore).

Plugin git repositories are listed in the [plugin table](site:help/#quick-links-wip).

## AI Use Policy

Please be sure to follow the [Pulp policy on AI Usage](site:help/more/governance/ai_policy/).

## Checklist

1. Add `functional tests` or `unit tests` where appropriate and ensure tests
   are passing on the CI.
2. Add a [`CHANGES entry`](site:pulpcore/docs/dev/guides/git/#markdown-header-changelog-update).
3. Update relevent `documentation`. Please build the docs to test!
4. If the PR is a simple feature or a bugfix, [`rebase and squash`](site:pulpcore/docs/dev/guides/git/#markdown-header-rebasing-and-squashing) to a single commit.
   If the PR is a complex feature, make sure that all commits are cleanly separated and have meaningful commit messages.
5. Make sure you tag commits with `closes #IssueNumber` or `ref #IssueNumber` when working on a tracked issue.
6. If AI was used, make sure you are following the [Pulp policy on AI Usage](site:help/more/governance/ai_policy/)
7. Push your branch to your fork and open a [Pull request across forks](https://help.github.com/articles/creating-a-pull-request-from-a-fork/).
8. If the change requires a corresponding change in `pulp-cli`, etc - file an issue and make an effort to make the 
   appropriate change - other developers would be glad to help.

## Review

Before a pull request can be merged, the `tests` must pass and it must
be reviewed. We encourage you to `reach out to the developers` to get speedy review.

## To Cherry-Pick or Not

If you are fixing a bug that should also be backported to another branch than `main`, add the
backport label, .e.g `backport-3.18`. PR authors can also add or remove this label if they have
write access.
