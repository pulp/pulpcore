.. _istqb: https://www.istqb.org/downloads/syllabi/foundation-level-syllabus.html
.. _Pulp Smash: https://github.com/PulpQE/pulp-smash/
.. _continuous-integration:

Continuous Integration
======================

Unit Tests
----------

New code is highly encouraged to have basic unit tests that demonstrate that
units (function, method or class instance) are working correctly.

A Pull Request that has failing unit tests cannot be merged.

The unit tests for `pulpcore` are in `pulpcore/tests
<https://github.com/pulp/pulpcore/tree/master/pulpcore/tests/unit>`_.

The unit tests for `pulpcore-plugin` are in `pulpcore-plugins/tests
<https://github.com/pulp/pulpcore/tree/master/plugin/tests/unit/>`_.

Functional Tests
----------------

Functional tests verify a specific feature.
In general functional tests tend to answer the question "As an user can I do this?"

Functional tests for Pulp are written using `Pulp Smash`_ . Pulp smash is a test
toolkit written to ease the testing of Pulp.

It is highly encouraged to accompany new features with functional
tests in `pulpcore/functional
<https://github.com/pulp/pulpcore/tree/master/pulpcore/tests/functional>`_.

Only the tests for features related to `pulpcore` should live in this repository.

Functional tests for features related to a specific plugin should live in the
plugin repository itself. For example:

  * `File Plugin
    <https://github.com/pulp/pulp_file/tree/master/pulp_file/tests/functional>`_

  * `RPM Plugin
    <https://github.com/pulp/pulp_rpm/tree/master/pulp_rpm/tests/functional>`_

Requiring other Pull Requests
-----------------------------

When a Pull Request breaks any test, it is the responsibility of the author to
fix the failing test. Fixing the tests may require an update of the `pulp_file`
plugin in addition to any `pulp-smash` changes. Once additional Pull Requests
for `pulp-smash` and `pulp_file` have been created, links to them can be
specified in the commit message of the Pull Request against `pulp`::

    Required PR: https://github.com/PulpQE/pulp-smash/pull/1234
    Required PR: https://github.com/pulp/pulp_file/pull/2345

This will allow the PR against pulp to run against the Pull Requests for pulp-smash and pulp_file.

Attention and care must be given to merging PRs that require other Pull Requests. Before merging,
all required PRs should be ready to merge--meaning that all tests/checks should be passing, the code
review requirements should be met, etc. When merging, the PR along with its required PRs should all
be merged at the same time. This is necessary to ensure that test breakages don't block other PRs.

Contributing to tests
----------------------
A new version of Pulp will only be released when all unit and functional are
passing.

Contributing test is a great way to ensure that your workflows never regress.

