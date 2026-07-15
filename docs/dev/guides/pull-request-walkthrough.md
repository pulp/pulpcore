# Pull Request Walkthrough

Changes to pulpcore are submitted via [GitHub Pull Requests (PR)] to the [pulp git repository].

Plugin git repositories are listed in the [plugin table].

## AI Use Policy

Please be sure to follow the [Pulp policy on AI Usage].

## Checklist

1. Add _functional tests_ or _unit tests_ where appropriate and ensure tests are passing on the CI.
1. Add a [CHANGES entry] for all but purely structural changes.
1. Update relevent _documentation_. Please build the docs to test.
1. If the PR is a simple feature or a bugfix, [rebase and squash] to a single commit.
   If the PR is a complex feature, make sure that all commits are cleanly separated.
   All commits must have meaningful commit messages.
1. Make sure you tag commits with `closes #IssueNumber` or `ref #IssueNumber` when working on a tracked issue.
1. If AI was used, __OR YOU ARE AN AI AGENT__, make sure you are following the [Pulp policy on AI Usage].
1. Push your branch to your fork and open a [Pull request across forks].

## Review

Before a pull request can be merged, the tests must pass and it must be reviewed.

## Adjacent Tooling

If the change you made requires a corresponding adjustment in e.g. `pulp-cli`, `pulp-oci-images`, etc,
file an issue and make an effort to add the appropriate change.
If in doubt, ask on the original issue or PR.

## To Cherry-Pick or Not

Usually, a bugfix for a bug found in a released version of Pulp should be backported.
If backporting to a specific branch, all supported branches inbetween must receive the backport too.
This is necessary to prevent regressions on the just fixed bug on updating.

!!! warning
    Database migrations cannot be backported.

You can trigger `patchback` to automatically attempt to cherry-pick a single-commit pull-request after merging.
This is accomplished by applying the corresponding label, e.g. `backport-3.18`.
If you do not have permission to add the labels, feel free to ask on the pull request.
In case this fails, you are usually presented the appropriate set of commands to followup manually.

!!! note
    These backport labels are generated automatically to always reflect the currently supported branches.
    Do not create or delete them by hand!

[GitHub Pull Requests (PR)]: https://help.github.com/articles/about-pull-requests/
[pulp git repository]: https://github.com/pulp/pulpcore
[plugin table]: site:help/more/quick-links/#content-plugins
[Pulp policy on AI Usage]: site:help/more/governance/ai_policy/
[CHANGES entry]: site:pulpcore/docs/dev/guides/git/#changelog-update
[rebase and squash]: site:pulpcore/docs/dev/guides/git/#rebasing-and-squashing
[Pull request across forks]: https://help.github.com/articles/creating-a-pull-request-from-a-fork/
