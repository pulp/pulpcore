=========
Changelog
=========

..
    You should *NOT* be adding new change log entries to this file, this
    file is managed by towncrier. You *may* edit previous change logs to
    fix problems like typo corrections or such.
    To add a new change log entry, please see
    https://docs.pulpproject.org/en/3.0/nightly/contributing/git.html#changelog-update

    WARNING: Don't drop the next directive!

.. towncrier release notes start

3.0.0rc3 (2019-06-28)
=====================

Features
--------

- Pulp now works with webserver configured authentication that use the ``REMOTE_USER`` method. Also a
  new setting ``REMOTE_USER_ENVIRON_NAME`` is introduced allowing webserver authentication to work in
  reverse proxy deployments.
  `#3808 <https://pulp.plan.io/issues/3808>`_
- Changing chunked uploads to use sha256 instead of md5
  `#4486 <https://pulp.plan.io/issues/4486>`_
- Adding support for parallel chunked uploads
  `#4488 <https://pulp.plan.io/issues/4488>`_
- Each Content App now heartbeats periodically, and Content Apps with recent heartbeats are shown in
  the Status API ``/pulp/api/v3/status/`` as a list called ``online_content_apps``. A new setting is
  introduced named ``CONTENT_APP_TTL`` which specifies the maximum time (in seconds) a Content App can
  not heartbeat and be considered online.
  `#4881 <https://pulp.plan.io/issues/4881>`_
- The task API now accepts PATCH requests that update the state of the task to 'canceled'. This
  replaces the previous task cancelation API.
  `#4883 <https://pulp.plan.io/issues/4883>`_
- Added support for removing all content units when creating a repo version by specifying '*'.
  `#4901 <https://pulp.plan.io/issues/4901>`_
- Added endpoint to delete uploads. Also added complete filter.
  `#4988 <https://pulp.plan.io/issues/4988>`_


Bugfixes
--------

- Core's serializer should only validate when policy='immediate' (the default).
  `#4990 <https://pulp.plan.io/issues/4990>`_


Improved Documentation
----------------------

- Adds an `authentication section <https://docs.pulpproject.org/en/3.0/nightly/installation/
  authentication.html>`_ to the installation guide. Also add two documented settings:
  ``AUTHENTICATION_BACKENDS`` and ``REMOTE_USER_ENVIRON_NAME``.
  `#3808 <https://pulp.plan.io/issues/3808>`_
- Switch to using `towncrier <https://github.com/hawkowl/towncrier>`_ for better release notes.
  `#4875 <https://pulp.plan.io/issues/4875>`_
- Adds documentation about the ``CONTENT_APP_TTL`` setting to the configuration page.
  `#4881 <https://pulp.plan.io/issues/4881>`_
- The term 'lazy' and 'Lazy' is replaced with 'on-demand' and 'On-Demand' respectively.
  `#4990 <https://pulp.plan.io/issues/4990>`_


Deprecations and Removals
-------------------------

- The migrations are squashed, requiring users of RC3 to deploy onto a fresh database so migrations
  can be applied again. This was due to alterations made to migration 0001 during the upload work.
  `#4488 <https://pulp.plan.io/issues/4488>`_
- All the string fields in the REST API no longer accept an empty string as a value. These fields now
  accept null instead.
  `#4676 <https://pulp.plan.io/issues/4676>`_
- The `Remote.validate` field is removed from the database and Remote serializer.
  `#4714 <https://pulp.plan.io/issues/4714>`_
- The task cancelation REST API has been removed.
  `#4883 <https://pulp.plan.io/issues/4883>`_


----


