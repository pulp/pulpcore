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

0.1.0rc7 (2019-10-15)
=====================


Features
--------

- Add new `repo_key` class attribute to `Content` which defaults to an empty tuple. Subclasses should
  use `repo_key` to specify the names of fields, which together should be unique per Repository.
  Anytime `RepositoryVersion.add_content()` is called, it now automatically removes content that
  matches the `repo_key`.
  `#5008 <https://pulp.plan.io/issues/5008>`_
- Add a ReadOnlyContentViewSet for plugin writers.
  `#5535 <https://pulp.plan.io/issues/5535>`_


Bugfixes
--------

- Fix `fields` filter for `SingleArtifactContentUploadSerializer`
  `#5543 <https://pulp.plan.io/issues/5543>`_


Improved Documentation
----------------------

- Document explicit definition of ref_name on the serializer.
  `#5562 <https://pulp.plan.io/issues/5562>`_


Deprecations and Removals
-------------------------

- Remove pulpcore.plugin.tasking.Task and expose pulpcore.models.Task instead.
  `#5442 <https://pulp.plan.io/issues/5442>`_
- Change `_id`, `_created`, `_last_updated`, `_href` to `pulp_id`, `pulp_created`, `pulp_last_updated`, `pulp_href`
  `#5457 <https://pulp.plan.io/issues/5457>`_
- Removing `non_fatal_errors` from `Task`.
  `#5537 <https://pulp.plan.io/issues/5537>`_


----


0.1.0rc6.dev (2019-09-30)
=========================


Features
--------

- Setting `code` on `ProgressBar`.
  `#5184 <https://pulp.plan.io/issues/5184>`_
- PublishedMetadata.create_from_file() interface added for creating PublishedMetadata.
  `#5304 <https://pulp.plan.io/issues/5304>`_
- Add SingleArtifactContentUploadSerializer a base class for content serializers that accept uploaded files.
  `#5403 <https://pulp.plan.io/issues/5403>`_
- DeclarativeArtifacts can have an Artifact without a RemoteArtifact.
  `#5413 <https://pulp.plan.io/issues/5413>`_
- Added `plugin_managed` field on repository that plugins can set for repositories that should be managed by plugins and not by users.
  `#5421 <https://pulp.plan.io/issues/5421>`_


Improved Documentation
----------------------

- Update docs removing database agnostic gotchas.
  `#5129 <https://pulp.plan.io/issues/5129>`_


Deprecations and Removals
-------------------------

- Remove support for mysql/mariadb making postgresql the only supported database.
  `#5129 <https://pulp.plan.io/issues/5129>`_
- PublishedMetadata should no longer be created using the default constructor.
  `#5304 <https://pulp.plan.io/issues/5304>`_
- Replace `ProgressBar` with `ProgressReport` and removing `ProgressSpinner`.
  `#5444 <https://pulp.plan.io/issues/5444>`_
- Remove custom JSONField implementation from public API
  `#5465 <https://pulp.plan.io/issues/5465>`_


Misc
----

- `#5444 <https://pulp.plan.io/issues/5444>`_


----


0.1.0rc5.dev (2019-09-10)
=========================


Features
--------

- Expose CharInFilter to plugins, which can filter by lists of strings.
  `#5182 <https://pulp.plan.io/issues/5182>`_
- Plugin writers can now define settings programatically.
  `#5290 <https://pulp.plan.io/issues/5290>`_


Bugfixes
--------

- Breaking change on how to subclass Master/Detail models in plugins, now `default_related_name` is required for Detail models.
  `#4681 <https://pulp.plan.io/issues/4681>`_
- Fixes `too many open files` when trying to perform large syncs with many downloads.
  `#5323 <https://pulp.plan.io/issues/5323>`_


Improved Documentation
----------------------

- Updating docs for subclassing models.
  `#4681 <https://pulp.plan.io/issues/4681>`_
- Added documentation on how to add settings programatically.
  `#5290 <https://pulp.plan.io/issues/5290>`_


----


0.1.0rc4 (2019-07-25)
=====================


Features
--------

- The ``DigestValidationError`` and ``SizeValidationError`` are available in the
  ``pulpcore.plugin.exceptions`` package.
  `#5077 <https://pulp.plan.io/issues/5077>`_
- The ``HyperlinkRelatedFilter`` is available in the ``pulpcore.plugin.viewsets`` submodule.
  `#5103 <https://pulp.plan.io/issues/5103>`_


Improved Documentation
----------------------

- Adds a new page and various updates with ``ContentGuard`` documentation for plugin writers.
  `#3972 <https://pulp.plan.io/issues/3972>`_
- Removed beta changelog entries to shorten the changelog.
  `#5166 <https://pulp.plan.io/issues/5166>`_


----


0.1.0rc3 (2019-06-28)
=====================


Bugfixes
--------

- Fixes use of the proxy URL when syncing from a remote.
  `#5011 <https://pulp.plan.io/issues/5011>`_


Improved Documentation
----------------------

- Switch to using `towncrier <https://github.com/hawkowl/towncrier>`_ for better release notes.
  `#4875 <https://pulp.plan.io/issues/4875>`_
- The term 'lazy' and 'Lazy' is replaced with 'on-demand' and 'On-Demand' respectively.
  `#4990 <https://pulp.plan.io/issues/4990>`_


Deprecations and Removals
-------------------------

- The `RemoteSerializer.policy` attribute in the plugin API had its choices restricted to only
  'immediate'. Plugin writers wanting to use 'on_demand' or 'streamed' as values for 'policy' should
  redefine the 'policy' attribute on the detail Remote.
  `#4990 <https://pulp.plan.io/issues/4990>`_


----


