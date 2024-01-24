# Git

Pulp source code lives on [GitHub](https://github.com/pulp/pulpcore). This document is definitive
for `pulpcore` only, but some plugins may choose to follow the same strategies.



## Versions and Branches

Code is submitted by a Pull Request on Github to merge the changes to `main` which represents
the next `pulpcore` release. See `versioning` for more details.

## Commits



### Rebasing and Squashing

We prefer each pull request to contain a single commit. Before you submit a PR, please consider an
[interactive rebase and squash.](https://github.com/edx/edx-platform/wiki/How-to-Rebase-a-Pull-Request)

The `git commit --amend` command is very useful, but be sure that you [understand what it does](https://www.atlassian.com/git/tutorials/rewriting-history/git-commit--amend) before you use it!
GitHub will update the PR and keep the comments when you force push an amended commit.

!!! warning
Keep in mind that rebasing creates new commits that are unique from your
original commits. Thus, if you have three commits and rebase them, you must
make sure that all copies of those original commits get deleted. Did you push
your branch to origin? Delete it and re-push after the rebase.




### Commit Message

Commit messages in Pulp should contain a human readable explanation of what was fixed.  They should
also follow the standard git message format of starting with a subject line or title (usually
wrapped at about 50 chars) and optionally, a longer message (usually wrapped at 72 characters)
broken up into paragraphs. For more on what constitutes a good commit message, we recommend [Tim
Pope's blog post on the subject](http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html).

Each commit message should link to an issue on the [pulpcore Github Issue tracker](https://github.com/pulp/pulpcore/issues/). See the [Github Linking Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue#linking-a-pull-request-to-an-issue-using-a-keyword) and include at least one link in your commit message.

If you must create a commit for which there is no issue, add the `[noissue]` syntax in the commit
message.

Putting this all together, the following is an example of a good commit message:

```
Update install and quickstart

The install docs and quickstart was leaving out an important step on
the worker configuration.

closes #1392
```

!!! tip
A good candidate for a `noissue` tag is a one line fix or a typo, otherwise we encourage
you to open an issue.




### Requiring other Pull Requests

Sometimes a new feature may require changes to both `pulpcore` and one or many other plugins.
However, plugins can only depend on features that are already released with `pulpcore` or any other
dependency. Sometimes though you need to demonstrate, that a new feature about to be added to
`pulpcore` will work with a corresponding plugin change before you can get the needed approvals. In
order to do so, you can depend the plugin's pull request on the head of the pull request or the
main branch of `pulpcore` in the following way:

Add a line like:

```
git+https://github.com/pulp/pulpcore@refs/pull/1234/head
git+https://github.com/pulp/pulpcore@refs/heads/main
```

to `ci_requirements.txt` in the plugin PR. Make sure that file is covered by `MANIFEST.in`. Also
bump the requirement on `pulpcore` in `requirements.txt` to at least the current `dev` version if
you want to be sure the `lower bounds` scenario passes.

This works accordingly for depending on other plugins.

This will allow the tests in the CI to run, but it will fail the `ready-to-ship` check. The
depended on PR must be merged **and** released before a PR like this can be merged.

For very similar reasons it can happen that you need changes to the base image used in the CI to
spin up a new pulp container. In those cases you can build your own modified version of the image
and push it to a container registry. Now you can specify the image to use in the last commit
message like:

```
CI Base Image: pulp/pulp-ci:special_feature
```

Attention and care must be given not to merge PRs that require custom CI images.



### Changelog update

The CHANGES.rst file is managed using the [towncrier tool](https://github.com/hawkowl/towncrier)
and all non trivial changes must be accompanied by a news entry.

For user facing changes, put those news files into `CHANGES/`. For Plugin API changes, put those
into the `CHANGES/plugin_api/` folder.

To add an entry to the news file, you first need an issue on github describing the change you
want to make. Once you have an issue, take its number and create a file inside of the `CHANGES/`
or `CHANGES/plugin_api/` directory named after that issue number with one of the extensions below.

| extension    | description                                                          |
| ------------ | -------------------------------------------------------------------- |
| .bugfix      | A bug fix                                                            |
| .feature     | A new feature                                                        |
| .removal     | A backwards incompatible change (ie a removal or change in behavior) |
| .deprecation | Information about an upcoming backwards incompatible change          |
| .doc         | A documentation improvement                                          |
| .misc        | A change that is not visible to the end user                         |

So if your user-facing issue is 3543 and it fixes a bug, you would create the file
`CHANGES/3543.bugfix`. Or if your plugin API change is 5432 and it's a breaking change you would
create the file `CHANGES/plugin_api/5432.removal`.

PRs can span multiple categories by creating multiple files (for instance, if you added a feature
and deprecated an old feature at the same time, you would create CHANGES/NNNN.feature and
CHANGES/NNNN.removal). Likewise if a PR touches multiple issues/PRs you may create a file for each
of them with the exact same contents and Towncrier will deduplicate them.

The contents of this file are reStructuredText formatted text that will be used as the content of
the news file entry. You do not need to reference the issue or PR numbers here as towncrier will
automatically add a reference to all of the affected issues when rendering the news file.

The changelog message should use past simple tense. When possible, the message should describe the
change being made as opposed to the problem or user story. Here are some examples:

- Added API that allows users to export a repository version to disk.
- Fixed bug where whitespace was being trimmed from uploaded files.
- Added documentation for new pulpcore-manager command.
