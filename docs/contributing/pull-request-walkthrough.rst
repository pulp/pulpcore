Pull Request Walkthrough
========================

Changes to pulpcore are submitted via `GitHub Pull Requests (PR)
<https://help.github.com/articles/about-pull-requests/>`_ to the `pulp git repository
<https://github.com/pulp/pulpcore>`_ . Plugin git repositories are listed in the `plugin table
<https://pulpproject.org/pulp-3-plugins/>`_.

Boilerplate
-----------

If you would like to submit a patch, especially if you have a major change, it is recommended that
you :ref:`chat with us<community>` before you get started.

#. `Fork <https://help.github.com/articles/fork-a-repo/>`_
   `pulpcore <https://github.com/pulp/pulpcore>`_ in your GitHub account.
#. :doc:`Install Pulp from source.<dev-setup/index>`
#. Create a new branch from the :ref:`appropriate base branch<git-branch>`
#. Review the :doc:`style-guide`.

Checklist
---------

#. Add :ref:`unit tests<continuous-integration>` where appropriate.
#. Update relevent :doc:`documentation`. Please build the docs to test!
#. If your change would benefit from integration testing, write a `pulp smash issue
   <https://github.com/PulpQE/pulp-smash/issues/new>`_.
#. If you are adding a new feature, add a release note.
#. :ref:`Rebase and squash<rebase>` to a single commit, if appropriate.
#. Write an excellent :ref:`commit-message`. Make sure you reference and link to the issue.
#. Push your branch to your fork and open a `Pull request across forks
   <https://help.github.com/articles/creating-a-pull-request-from-a-fork/>`_.
#. Add GitHub labels as appropriate.
#. Change the status of the redmine issue to "POST".
#. Add a link to the pull request in a comment on the issue.

Review
------

Before a pull request can be merged, the :ref:`tests<continuous-integration>` must pass and it must
be reviewed by one of the committers. We encourage you to :ref:`reach out to the
developers<community>` to get speedy review.

.. note::
   *To the community:* The Pulp Team is very grateful for your contribution and values your
   involvement tremendously! There are few things in an OSS project as satisfying as receiving a
   pull request from the community.

   We are very open and honest when we review each other's work. We will do our best to review your
   contribution with respect and professionalism. In return, we hope you will accept our review
   process as an opportunity for everyone to learn something, and to make Pulp the best project it
   can be. If you are uncertain about comments or instructions, please let us know!
