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

3.0.0rc7 (2019-10-15)
=====================

Features
--------

- Setting `code` on `ProgressReport` for identifying the type of progress report.
  `#5184 <https://pulp.plan.io/issues/5184>`_
- Add the possibility to pass context to the general_create task.
  `#5403 <https://pulp.plan.io/issues/5403>`_
- Filter plugin managed repositories.
  `#5421 <https://pulp.plan.io/issues/5421>`_
- Using `ProgressReport` for known and unknown items count.
  `#5444 <https://pulp.plan.io/issues/5444>`_
- Expose `exclude_fields` the api schema and bindings to allow users to filter out fields.
  `#5519 <https://pulp.plan.io/issues/5519>`_


Bugfixes
--------

- PublishedMetadata files are now stored in artifact storage.
  `#5304 <https://pulp.plan.io/issues/5304>`_
- Fix 500 on Schemas.
  `#5311 <https://pulp.plan.io/issues/5311>`_
- /etc/pulp/settings.py override default settings provided by plugins.
  `#5425 <https://pulp.plan.io/issues/5425>`_
- Fixing error where relative_path was defined on model but not serializer
  `#5445 <https://pulp.plan.io/issues/5445>`_
- Fixed issue where removing all units on a repo with no version threw an error.
  `#5478 <https://pulp.plan.io/issues/5478>`_
- content-app sets Content-Type and Content-Encoding headers for all responses.
  `#5507 <https://pulp.plan.io/issues/5507>`_
- Fix erroneous namespacing for Detail viewsets that don't inherit from Master viewsets.
  `#5533 <https://pulp.plan.io/issues/5533>`_


Improved Documentation
----------------------

- Update installation docs since mariadb/mysql is no longer supported.
  `#5129 <https://pulp.plan.io/issues/5129>`_


Deprecations and Removals
-------------------------

- By default, html in field descriptions filtered out in REST API docs unless 'include_html' is set.
  `#5009 <https://pulp.plan.io/issues/5009>`_
- Remove support for mysql/mariadb making postgresql the only supported database.
  `#5129 <https://pulp.plan.io/issues/5129>`_
- Creating a progress report now requires setting code field.
  `#5184 <https://pulp.plan.io/issues/5184>`_
- Rename the fields on the ContentSerializers to not start with underscore.
  `#5428 <https://pulp.plan.io/issues/5428>`_
- Removing `ProgressSpinner` and `ProgressBar` models.
  `#5444 <https://pulp.plan.io/issues/5444>`_
- Change `_type` to `pulp_type`
  `#5454 <https://pulp.plan.io/issues/5454>`_
- Change `_id`, `_created`, `_last_updated`, `_href` to `pulp_id`, `pulp_created`, `pulp_last_updated`, `pulp_href`
  `#5457 <https://pulp.plan.io/issues/5457>`_
- Remove custom JSONField implementation from public API
  `#5465 <https://pulp.plan.io/issues/5465>`_
- Delete NamePagination class and use sorting on the queryset instead.
  `#5489 <https://pulp.plan.io/issues/5489>`_
- Removing filter for `plugin_managed` repositories.
  `#5516 <https://pulp.plan.io/issues/5516>`_
- Renamed `fields!` to `exclude_fields` since exclamation mark is a special char in many languages.
  `#5519 <https://pulp.plan.io/issues/5519>`_
- Removed the logic that automatically defines the namespace for Detail model viewsets when there is no Master viewset.
  `#5533 <https://pulp.plan.io/issues/5533>`_
- Removing `non_fatal_errors` from `Task`.
  `#5537 <https://pulp.plan.io/issues/5537>`_
- Remove "_" from `_versions_href`, `_latest_version_href`
  `#5548 <https://pulp.plan.io/issues/5548>`_
- Removing base serializer field: `_type` .
  `#5550 <https://pulp.plan.io/issues/5550>`_


Misc
----

- `#4554 <https://pulp.plan.io/issues/4554>`_, `#5008 <https://pulp.plan.io/issues/5008>`_, `#5535 <https://pulp.plan.io/issues/5535>`_, `#5565 <https://pulp.plan.io/issues/5565>`_


----


3.0.0rc6 (2019-10-01)
=====================

Features
--------

- Setting `code` on `ProgressReport` for identifying the type of progress report.
  `#5184 <https://pulp.plan.io/issues/5184>`_
- Add the possibility to pass context to the general_create task.
  `#5403 <https://pulp.plan.io/issues/5403>`_
- Filter plugin managed repositories.
  `#5421 <https://pulp.plan.io/issues/5421>`_
- Using `ProgressReport` for known and unknown items count.
  `#5444 <https://pulp.plan.io/issues/5444>`_


Bugfixes
--------

- PublishedMetadata files are now stored in artifact storage.
  `#5304 <https://pulp.plan.io/issues/5304>`_
- Fixing error where relative_path was defined on model but not serializer
  `#5445 <https://pulp.plan.io/issues/5445>`_
- Fixed issue where removing all units on a repo with no version threw an error.
  `#5478 <https://pulp.plan.io/issues/5478>`_
- content-app sets Content-Type and Content-Encoding headers for all responses.
  `#5507 <https://pulp.plan.io/issues/5507>`_


Improved Documentation
----------------------

- Update installation docs since mariadb/mysql is no longer supported.
  `#5129 <https://pulp.plan.io/issues/5129>`_


Deprecations and Removals
-------------------------

- By default, html in field descriptions filtered out in REST API docs unless 'include_html' is set.
  `#5009 <https://pulp.plan.io/issues/5009>`_
- Remove support for mysql/mariadb making postgresql the only supported database.
  `#5129 <https://pulp.plan.io/issues/5129>`_
- Creating a progress report now requires setting code field.
  `#5184 <https://pulp.plan.io/issues/5184>`_
- Rename the fields on the ContentSerializers to not start with underscore.
  `#5428 <https://pulp.plan.io/issues/5428>`_
- Removing `ProgressSpinner` and `ProgressBar` models.
  `#5444 <https://pulp.plan.io/issues/5444>`_
- Remove custom JSONField implementation from public API
  `#5465 <https://pulp.plan.io/issues/5465>`_
- Delete NamePagination class and use sorting on the queryset instead.
  `#5489 <https://pulp.plan.io/issues/5489>`_


----


3.0.0rc5 (2019-09-10)
=====================

Features
--------

- Allow users to filter tasks by created resources
  `#4931 <https://pulp.plan.io/issues/4931>`_
- Enable users to filter tasks by reserved resources
  `#5120 <https://pulp.plan.io/issues/5120>`_
- Add CharInFilter that allows filtering CharField by mutiple values
  `#5182 <https://pulp.plan.io/issues/5182>`_
- Pinning pulpcore dependencies to y releases
  `#5196 <https://pulp.plan.io/issues/5196>`_


Bugfixes
--------

- Adding fields parameter to OpenAPI schema.
  `#4992 <https://pulp.plan.io/issues/4992>`_
- Improved the OpenAPI schema for RepositoryVersion.content_summary.
  `#5210 <https://pulp.plan.io/issues/5210>`_
- Switch default DRF pagination to use LimitOffset style instead of Page ID.
  `#5324 <https://pulp.plan.io/issues/5324>`_


Improved Documentation
----------------------

- Update REST API docs for `uploads_commit`.
  `#5190 <https://pulp.plan.io/issues/5190>`_
- Removed beta changelog entries to shorten the changelog.
  `#5208 <https://pulp.plan.io/issues/5208>`_


Deprecations and Removals
-------------------------

- Removing code from task errors.
  `#5282 <https://pulp.plan.io/issues/5282>`_
- All previous bindings expect a different pagination style and are not compatible with the pagination
  changes made. Newer bindings are available and should be used.
  `#5324 <https://pulp.plan.io/issues/5324>`_


Misc
----

- `#4681 <https://pulp.plan.io/issues/4681>`_, `#5210 <https://pulp.plan.io/issues/5210>`_, `#5290 <https://pulp.plan.io/issues/5290>`_


----


3.0.0rc4 (2019-07-25)
=====================

Features
--------

- Allow users to pass sha256 with each chunk to have Pulp verify the chunk.
  `#4982 <https://pulp.plan.io/issues/4982>`_
- Users can view chunks info for chunked uploads in the API
  `#5150 <https://pulp.plan.io/issues/5150>`_


Bugfixes
--------

- Setting missing fields on orphan cleanup tasks.
  `#4662 <https://pulp.plan.io/issues/4662>`_
- Allow user to filter created resources without providing _href in a query
  `#4722 <https://pulp.plan.io/issues/4722>`_
- GET of a ``Distribution`` without configuring the ``CONTENT_HOST`` setting no longer causes a 500
  error.
  `#4945 <https://pulp.plan.io/issues/4945>`_
- Increased artifact size field to prevent 500 errors for artifacts > 2GB in size.
  `#4998 <https://pulp.plan.io/issues/4998>`_
- Allow artifacts to be created using json
  `#5016 <https://pulp.plan.io/issues/5016>`_
- Have the commit endpoint dispatch a task to create artifacts from chunked uploads
  `#5087 <https://pulp.plan.io/issues/5087>`_
- Allow user to delete uploaded content from a local file system when the artifact creation fails
  `#5092 <https://pulp.plan.io/issues/5092>`_


Improved Documentation
----------------------

- Fix broken urls in the ``/installation/configuration.html#settings`` area.
  `#5160 <https://pulp.plan.io/issues/5160>`_


Deprecations and Removals
-------------------------

- Switched the default of the ``CONTENT_HOST`` setting from ``None`` to ``''``.
  `#4945 <https://pulp.plan.io/issues/4945>`_
- Removed upload parameter from artifact create endpoint and converted upload commit to return 202.
  `#5087 <https://pulp.plan.io/issues/5087>`_


----


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


