Git
===

Pulp source code lives on `GitHub <https://github.com/pulp/pulpcore>`_. This document is definitive
for :term:`pulpcore` only, but some plugins may choose to follow the same strategies.

.. _git-branch:

Versions and Branches
---------------------

Code is submitted by a Pull Request on Github to merge the changes to ``master`` which represents
the next ``pulpcore`` release. See :ref:`versioning` for more details.


Commits
-------

.. _rebase:

Rebasing and Squashing
**********************

We prefer each pull request to contain a single commit. Before you submit a PR, please consider an
`interactive rebase and squash.
<https://github.com/edx/edx-platform/wiki/How-to-Rebase-a-Pull-Request>`_

The ``git commit --amend`` command is very useful, but be sure that you `understand what it does
<https://www.atlassian.com/git/tutorials/rewriting-history/git-commit--amend>`_ before you use it!
GitHub will update the PR and keep the comments when you force push an amended commit.

.. warning::
   Keep in mind that rebasing creates new commits that are unique from your
   original commits. Thus, if you have three commits and rebase them, you must
   make sure that all copies of those original commits get deleted. Did you push
   your branch to origin? Delete it and re-push after the rebase.

.. _commit-message:

Commit Message
**************

Commit messages in Pulp should contain a human readable explanation of what was fixed.  They should
also follow the standard git message format of starting with a subject line or title (usually
wrapped at about 50 chars) and optionally, a longer message (usually wrapped at 72 characters)
broken up into paragraphs. For more on what constitutes a good commit message, we recommend `Tim
Pope's blog post on the subject
<http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html>`_.

Each commit message should reference an issue in `Pulp's Redmine issue tracker
<https://pulp.plan.io>`_. To do this you should **include both a keyword and a link** to the issue.

To reference the issue (but not change its state), use ``re`` or ``ref``::

    re #123
    ref #123

To update the issue's state to MODIFIED and set the %done to 100, use
``fixes`` or ``closes``::

    fixes #123
    closes #123

To reference multiple issues in a commit use a separate line for each one::

    fixes #123
    fixes #124

We strongly suggest that each commit is attached to an issue in Redmine tracker. Our tracker is
a centralized point of reference, that keeps track of design decisions and discussions and is used
by the release process. However, if you must create a commit for which there is no issue,
add the tag ``[noissue]`` to the commit's message.

Putting this all together, the following is an example of a good commit message::

    Update node install and quickstart

    The nodes install and quickstart was leaving out an important step on
    the child node to configure the server.conf on the child node.

    closes #1392
    https://pulp.plan.io/issues/1392

.. hint::

   A good candidate for a ``noissue`` tag is a one line fix or a typo, otherwise we encourage
   you to open an issue.


.. _requiring-other-pull-requests:

Requiring other Pull Requests
*****************************

Sometimes a new feature may require changes to both `pulpcore` and one or many other plugins,
simultaneously. In order to keep the CI happy in these circumstances (as tests may fail otherwise),
we provide a mechanism to force the CI service to fetch the version of a component in a linked
Pull Request, rather than master branch.

To do so, add a tag in the following format to the last commit in your series.

This will allow the PR against pulp to run against the Pull Requests for pulp-smash and pulp_file::

    Required PR: https://github.com/pulp/pulp-smash/pull/1234
    Required PR: https://github.com/pulp/pulp_file/pull/2345

This will allow the PR against a plugin to run against the Pull Request for pulpcore::

    Required PR: https://github.com/pulp/pulpcore/pull/3456

Attention and care must be given to merging PRs that require other Pull Requests. Before merging,
all required PRs should be ready to merge--meaning that all tests/checks should be passing, the code
review requirements should be met, etc. When merging, the PR along with its required PRs should all
be merged at the same time. This is necessary to ensure that test breakages don't block other PRs.

For very similar reasons it can happen that you need changes to the base image used in the CI to
spin up a new pulp container. In those cases you can build your own modified version of the image
and push it to a container registry. Now you can specify the image to use in the last commit like::

    CI Base Image: pulp/pulp-ci:special_feature

The same meticulousness as described above is required to merge those Pull Requests.


.. _changelog-update:

Changelog update
****************

The CHANGES.rst file is managed using the `towncrier tool <https://github.com/hawkowl/towncrier>`_
and all non trivial changes must be accompanied by a news entry.

For user facing changes, put those news files into ``CHANGES/``. For Plugin API changes, put those
into the ``CHANGES/plugin_api/`` folder.

To add an entry to the news file, you first need an issue in pulp.plan.io describing the change you
want to make. Once you have an issue, take its number and create a file inside of the ``CHANGES/``
or ``CHANGES/plugin_api/`` directory named after that issue number with one of the extensions below.

+--------------+----------------------------------------------------------------------+
| extension    | description                                                          |
+==============+======================================================================+
| .bugfix      | A bug fix                                                            |
+--------------+----------------------------------------------------------------------+
| .feature     | A new feature                                                        |
+--------------+----------------------------------------------------------------------+
| .removal     | A backwards incompatible change (ie a removal or change in behavior) |
+--------------+----------------------------------------------------------------------+
| .deprecation | Information about an upcoming backwards incompatible change          |
+--------------+----------------------------------------------------------------------+
| .misc        | A change that is not visible to the end user                         |
+--------------+----------------------------------------------------------------------+

So if your user-facing issue is 3543 and it fixes a bug, you would create the file
``CHANGES/3543.bugfix``. Or if your plugin API change is 5432 and it's a breaking change you would
create the file ``CHANGES/plugin_api/5432.removal``.

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
