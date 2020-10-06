Bugs, Feature and Backport Requests
===================================

Bugs, feature and backport requests for :term:`pulpcore` are tracked with `Redmine
<https://pulp.plan.io/projects/pulp/issues/>`_. Please see the `plugin table
<https://pulpproject.org/content-plugins/>`_ for trackers for each plugin.

.. _issue-writing:

How to File an Issue
--------------------

`New pulpcore issue <https://pulp.plan.io/projects/pulp/issues/new>`_.

.. warning::
  Is this security related? If so, please follow the :ref:`security-bugs` procedure.

Please set **only the fields in this table**. See :ref:`redmine-fields` for more detailed
descriptions of all the fields and how they are used.

.. list-table::
   :header-rows: 1
   :widths: auto
   :align: center

   * - Field
     - Instructions

   * - Tracker
     - For a bug, select ``Issue``, for a feature-request, choose ``Story``,
       for a backport request, choose ``Backport``.

   * - Subject
     - Strive to be specific and concise.

   * - Description
     - This is the most important part! Please see :ref:`issue-description`.

   * - Category
     - Choose one if applicable, blank is OK.

   * - Version
     - The version of pulpcore that you discovered the issue.

   * - OS
     - Please select your operating system.

   * - Tags
     - For searching. Select 0 or many, best judgement.
       If an issue requires a functional test. Add the tag `Functional test`.

.. _issue-description:

Description Field
*****************

A well written description is very helpful to developers and other users with similar problems. It
is ok if you aren't able to provide all the information requested here, but clear and detailed
issues are more likely to be fixed quickly. Bonus points if they are `pretty
<https://www.redmine.org/projects/redmine/wiki/RedmineTextFormattingMarkdown>`_.

For **Issues** (Bugs)
^^^^^^^^^^^^^^^^^^^^^

Please include:

#. Detailed explanation of the problem. For problems involving external content sources, please
   indicate the source (and a link) if you can.
#. Clear steps to reproduce the problem. Commands and/or REST calls are highly encouraged.
#. Expected results
#. Actual results
#. Snippet of relevant logs, especially Exceptions.

You can also upload attachments, but please only upload relevant data. For example, if you have an
entire log which contains some errors, please trim it to just the relevant portions and upload
those.

For **Feature Requests** (Stories)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The description will depend on the feature. Please be specific when describing the requested
behavior and include the motivation for adding it. If you have suggestions for how the
commands/REST calls would look, please include that as well. Feature requests require follow-up
from the filer, so please :ref:`reach out<community>` with a link to your issue.

For **Backport Requests**
^^^^^^^^^^^^^^^^^^^^^^^^^

Only bug fixes from newer versions can be requested to be backported. No features can be backported
to older versions.

Django migrations are order dependent so we cannot backport any change that has database migrations.
Thus z-stream releases will not add new migrations.

Please include:

#. A redmine issue number or URL for the bug fix to backport. If possible, relate those two issues
   in the tracker using ``Add`` in the ``Related issues`` section after creating a Backport request.
#. The Y release of the component you need a backport for. E.g. pulpcore 3.4, pulp_file 1.0, etc.
#. The reasons for the backport request.

If a backport request is not accepted, it is closed as WONTFIX.


.. _triage:

Triage
------
Twice per week, the Pulp team triages all new bugs, at which point its *Severity* rating and other
aspects of the report will be evaluated. If necessary, the bug may be commented on requesting more
information or clarification from the reporter. When a bug has enough information, its *Priority*
rating set and is marked as triaged using the *Triaged* boolean.


.. _security-bugs:

Security Disclosures
--------------------

We take security issues seriously and welcome responsible disclosure of security vulnerabilities in
Pulp. Please email pulp-security@redhat.com (a private address for the Pulp Security Team) with all
reports.

Your report should include:

#. Pulp version
#. A vulnerability description
#. Reproduction steps
#. Feel free to submit a patch with your disclosure. A member of the Pulp Security Team will
   confirm the vulnerability, determine its impact, and develop a fix.

.. _redmine-fields:

Redmine Fields
--------------

+-------------+-----------------------------------------------------------------------------------+
| Field       | Description                                                                       |
+-------------+-----------------------------------------------------------------------------------+
| Tracker     | - ``Issue`` (bug) Defect in a feature that is expected to work.                   |
|             | - ``Story`` New feature or functionality.                                         |
|             | - ``Refactor`` Improvement that will not be visible to the user in any way.       |
|             | - ``Task`` Work that will not be a part of released code.                         |
|             | - ``Backport`` Requested backport.                                                |
|             | - ``Test`` Requested functional test.                                             |
+-------------+-----------------------------------------------------------------------------------+
| Subject     | - For an ``Issue``, summary of the situation and the unexpected result.           |
|             | - For a ``Story``, takes the form "As a [user/dev/etc] I can ..."                 |
|             | - For a ``Task`` or ``Refactor`` describe what should be done. in any way.        |
|             | - For a ``Backport``, takes the form "<redmine issue number> into                 |
|             |   <component><Y release>"                                                         |
+-------------+-----------------------------------------------------------------------------------+
| Description | A detailed explanation of the problem please see :ref:`issue-description`         |
+-------------+-----------------------------------------------------------------------------------+
| Status      | - ``NEW`` Unassigned, incomplete                                                  |
|             | - ``ASSIGNED`` Incomplete, assignee should also be set                            |
|             | - ``POST`` Pull Request is open (with a link in a comment)                        |
|             | - ``MODIFIED`` Change has been merged, but has not been released                  |
|             | - ``CLOSED`` If you disagree, please re-open and comment                          |
+-------------+-----------------------------------------------------------------------------------+
| Priority    | Assigned during :ref:`triage`.                                                    |
+-------------+-----------------------------------------------------------------------------------+
| Assignee    | Contributor who is working on this issue.                                         |
+-------------+-----------------------------------------------------------------------------------+
| Milestone   | A set of work that has been grouped together.                                     |
+-------------+-----------------------------------------------------------------------------------+
| Parent Task | Indicates that this is a sub-task of the larger issue.                            |
+-------------+-----------------------------------------------------------------------------------+
| Severity    | Assigned during :ref:`triage`.                                                    |
+-------------+-----------------------------------------------------------------------------------+
| Version     | Filer experienced the problem while running this version of pulpcore              |
+-------------+-----------------------------------------------------------------------------------+
| Platform    | - Indicates the earliest version that contains these changes                      |
| Release     | - This field is set only on issues that have been completed                       |
+-------------+-----------------------------------------------------------------------------------+
| Triaged     | Indicates whether an issue has gone through :ref:`bug triage<triage>`             |
+-------------+-----------------------------------------------------------------------------------+
| Groomed     | Core developers mark issues groomed when they include all necessary information.  |
+-------------+-----------------------------------------------------------------------------------+
| Sprint      | If set, indicates that the issue is accepted and is ready to be worked on.        |
+-------------+-----------------------------------------------------------------------------------+
| Tags        | Used for filtering.                                                               |
+-------------+-----------------------------------------------------------------------------------+
