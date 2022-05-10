Pull Request Walkthrough
========================

Changes to pulpcore are submitted via `GitHub Pull Requests (PR)
<https://help.github.com/articles/about-pull-requests/>`_ to the `pulp git repository
<https://github.com/pulp/pulpcore>`_ . Plugin git repositories are listed in the `plugin table
<https://pulpproject.org/content-plugins/>`_.

Checklist
---------

#. Add :ref:`functional tests<tests>` or :ref:`unit tests<tests>` where appropriate and ensure tests
   are passing on the CI.
#. Add a :ref:`CHANGES entry <changelog-update>`.
#. Update relevent :doc:`documentation`. Please build the docs to test!
#. :ref:`Rebase and squash<rebase>` to a single commit.
#. Write an excellent :ref:`commit-message`. Make sure you reference and link to the issue.
#. Push your branch to your fork and open a `Pull request across forks
   <https://help.github.com/articles/creating-a-pull-request-from-a-fork/>`_.
#. If the change requires a corresponding change in pulp-cli, open a PR against the pulp-cli or
   :doc:`file an issue</bugs-features>`.

Review
------

Before a pull request can be merged, the :ref:`tests<tests>` must pass and it must
be reviewed. We encourage you to :ref:`reach out to the developers<community>` to get speedy review.


To Cherry-Pick or Not
---------------------

If you are fixing a bug that should also be backported to another branch than ``main``, add the
backport label, .e.g ``backport-3.18``. PR authors can also add or remove this label if they have
write access.
