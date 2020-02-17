=========
Changelog
=========

..
    You should *NOT* be adding new change log entries to this file, this
    file is managed by towncrier. You *may* edit previous change logs to
    fix problems like typo corrections or such.
    To add a new change log entry, please see
    https://docs.pulpproject.org/contributing/git.html#changelog-update

    WARNING: Don't drop the next directive!

.. towncrier release notes start

3.1.1 (2020-02-17)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Content with duplicate repo_key_fields raises an error
  `#5567 <https://pulp.plan.io/issues/5567>`_
- Resolve content app errors ``django.db.utils.InterfaceError: connection already closed``.
  `#6045 <https://pulp.plan.io/issues/6045>`_
- Fix a bug that could cause an inability to detect an invalid signing script during the validation
  `#6077 <https://pulp.plan.io/issues/6077>`_
- Fixing broken S3 redirect
  `#6154 <https://pulp.plan.io/issues/6154>`_
- Pin `idna==2.8`` to avoid a version conflict caused by the idna 2.9 release.
  `#6169 <https://pulp.plan.io/issues/6169>`_


Plugin API
----------

Features
~~~~~~~~

- A new method ``_reset_db_connection`` has been added to ``content.Handler``. It can be called before
  accessing the db to ensure that the db connection is alive.
  `#6045 <https://pulp.plan.io/issues/6045>`_


----


3.1.0 (2020-01-30)
==================
REST API
--------

Features
~~~~~~~~

- Allow administrators to add a signing service
  `#5943 <https://pulp.plan.io/issues/5943>`_
- Adds ``pulpcore.app.authentication.PulpDoNotCreateUsersRemoteUserBackend`` which can be used to
  verify authentication in the webserver, but will not automatically create users like
  ``django.contrib.auth.backends.RemoteUserBackend`` does.
  `#5949 <https://pulp.plan.io/issues/5949>`_
- Allow Azure blob storage to be used as DEFAULT_FILE_STORAGE for Pulp
  `#5954 <https://pulp.plan.io/issues/5954>`_
- Allow to filter publications by ``repository_version`` and ``pulp_created``
  `#5968 <https://pulp.plan.io/issues/5968>`_
- Adds the ``ALLOWED_IMPORT_PATHS`` setting which can specify the file path prefix that ``file:///``
  remote paths can import from.
  `#5974 <https://pulp.plan.io/issues/5974>`_
- Allow the same artifact to be published at multiple relative paths in the same publication.
  `#6037 <https://pulp.plan.io/issues/6037>`_


Bugfixes
~~~~~~~~

- Files stored on S3 and Azure now download with the correct filename.
  `#4733 <https://pulp.plan.io/issues/4733>`_
- Adds operation_summary to the OpenAPI schema definition of repository modify operation
  `#6002 <https://pulp.plan.io/issues/6002>`_
- Temporarily pinned redis-py version to avoid a task locking issue.
  `#6038 <https://pulp.plan.io/issues/6038>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Rewrote the Authentication page for more clarity on how to configure Pulp's authentication.
  `#5949 <https://pulp.plan.io/issues/5949>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removed the ``django.contrib.auth.backends.RemoteUserBackend`` as a default configured backend in
  ``settings.AUTHENTICATION_BACKENDS``. Also removed
  ``pulpcore.app.authentication.PulpRemoteUserAuthentication`` from the DRF configuration of
  ``DEFAULT_AUTHENTICATION_CLASSES``.
  `#5949 <https://pulp.plan.io/issues/5949>`_
- Importing from file:/// now requires the configuration of the ``ALLOWED_IMPORT_PATHS`` setting.
  Without this configuration, Pulp will not import content from ``file:///`` locations correctly.
  `#5974 <https://pulp.plan.io/issues/5974>`_


Misc
~~~~

- `#5795 <https://pulp.plan.io/issues/5795>`_


Plugin API
----------

Features
~~~~~~~~

- Allow awaiting for resolution on DeclarativeContent.
  `#5668 <https://pulp.plan.io/issues/5668>`_
- Add a previous() method to RepositoryVersion.
  `#5734 <https://pulp.plan.io/issues/5734>`_
- Enable plugin writers to sign selected content with signing scripts provided by administrators
  `#5946 <https://pulp.plan.io/issues/5946>`_
- Add a batching content iterator ``content_batch_qs()`` to ``RepositoryVersion``.
  `#6024 <https://pulp.plan.io/issues/6024>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- The ```Handler._handle_file_response` has been removed. It was renamed to
  ``_serve_content_artifact`` and has the following signature::

      def _serve_content_artifact(self, content_artifact, headers):
  `#4733 <https://pulp.plan.io/issues/4733>`_
- Remove get_or_create_future and does_batch from DeclarativeContent. Replaced by awaiting for
  resolution on the DeclarativeContent itself.
  `#5668 <https://pulp.plan.io/issues/5668>`_


----


3.0.1 (2020-01-15)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fix bug where content shows as being added and removed in the same version.
  `#5707 <https://pulp.plan.io/issues/5707>`_
- Fix bug where calling Repository new_version() outside of task raises exception.
  `#5894 <https://pulp.plan.io/issues/5894>`_
- Adjusts setup.py classifier to show 3.0 as Production/Stable.
  `#5896 <https://pulp.plan.io/issues/5896>`_
- Importing from file:/// paths no longer destroys the source repository.
  `#5941 <https://pulp.plan.io/issues/5941>`_
- Webserver auth no longer prompts for csrf incorrectly.
  `#5955 <https://pulp.plan.io/issues/5955>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removed ``pulpcore.app.middleware.PulpRemoteUserMiddleware`` from the default middleware section.
  Also replaced ``rest_framework.authentication.RemoteUserAuthentication`` with
  ``pulpcore.app.authentication.PulpRemoteUserAuthentication`` in the Django Rest Framework portion
  of the config.
  `#5955 <https://pulp.plan.io/issues/5955>`_


Misc
~~~~

- `#5833 <https://pulp.plan.io/issues/5833>`_, `#5867 <https://pulp.plan.io/issues/5867>`_, `#5870 <https://pulp.plan.io/issues/5870>`_, `#5873 <https://pulp.plan.io/issues/5873>`_


Plugin API
----------

Features
~~~~~~~~

- Added an optional parameter base_version to RepositoryVersion add() and removed() methods.
  `#5706 <https://pulp.plan.io/issues/5706>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Saving an Artifact from a source that is outside of settings.MEDIA_ROOT will copy the file instead
  of moving the file as it did in previous versions. This causes data imported from file:/// sources
  to be left in tact.
  `#5941 <https://pulp.plan.io/issues/5941>`_


----


3.0.0 (2019-12-11)
==================

.. note::

    Task names, e.g. ``pulpcore.app.tasks.orphan.orphan_cleanup``, are subject to change in future
    releases 3.y releases. These are represented in the Task API as the "name" attribute. Please
    check future release notes to see when these names will be considered stable. Otherwise, the
    REST API pulpcore provides is considered semantically versioned.


REST API
--------

Features
~~~~~~~~

- Pulp will do validation that a new repository version contains only content which is supported by
  the Repository type. Using the same a-priori knowledge of content types, increase performance of
  duplicate removal.
  `#5701 <https://pulp.plan.io/issues/5701>`_


Bugfixes
~~~~~~~~

- Improve speed and memory performance.
  `#5688 <https://pulp.plan.io/issues/5688>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Fix an incorrect license claim in the docs. Pulp is GPLv2+.
  `#4592 <https://pulp.plan.io/issues/4592>`_
- Labeling 3.0 features as tech preview.
  `#5563 <https://pulp.plan.io/issues/5563>`_
- Simplified docs index page.
  `#5714 <https://pulp.plan.io/issues/5714>`_
- Add text to Promotion page.
  `#5721 <https://pulp.plan.io/issues/5721>`_
- Fixes and updates to the glossry page.
  `#5726 <https://pulp.plan.io/issues/5726>`_


Plugin API
----------

Features
~~~~~~~~

- Added a new required field called CONTENT_TYPES to the Repository model.
  `#5701 <https://pulp.plan.io/issues/5701>`_


----


3.0.0rc9 (2019-12-03)
=====================
REST API
--------

Features
~~~~~~~~

- Multiple resource-managers can be started and only one will be active.
  `#3707 <https://pulp.plan.io/issues/3707>`_
- Create an initial repo version when repos get created.
  `#5757 <https://pulp.plan.io/issues/5757>`_
- Workers no longer require names, and auto-name as {pid}@{fqdn}. This allows easy finding of
  processes from the Status API. Custom names still work by specifying the ``-n`` option when starting
  a worker. Any worker name starting with ``resource-manager`` is a resource-manager, otherwise it's
  assumed to be a task worker.
  `#5787 <https://pulp.plan.io/issues/5787>`_


Bugfixes
~~~~~~~~

- Release reservations for tasks when cleaned up by another worker.
  `#5673 <https://pulp.plan.io/issues/5673>`_
- Delete the repository version if an exception is raised during finalize_new_version().
  `#5712 <https://pulp.plan.io/issues/5712>`_
- Fix uncast Repository bug when modifying repository content.
  `#5728 <https://pulp.plan.io/issues/5728>`_
- Fix the pulp_type field output in __str__ for MasterModels.
  `#5733 <https://pulp.plan.io/issues/5733>`_
- Fix path parameter in OpenAPI schema for Repoistory Version endpoints.
  `#5760 <https://pulp.plan.io/issues/5760>`_
- Fix old references to ssl_ca_certificate and ssl_client_key.
  `#5770 <https://pulp.plan.io/issues/5770>`_
- Only online workers are shown in the ``/pulp/api/v3/status/`` causing environments where worker
  names change to not accumulate workers endlessly.
  `#5786 <https://pulp.plan.io/issues/5786>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added info about ``resource-manager`` High Availability to the docs.
  `#3707 <https://pulp.plan.io/issues/3707>`_
- Fixing a broken link to the Plugin API docs on the homepage.
  `#5660 <https://pulp.plan.io/issues/5660>`_
- Added content to the pulp2-to-3 documentation page.
  `#5715 <https://pulp.plan.io/issues/5715>`_
- Move the section "Static Content" to "Architecture and Deploying"
  `#5716 <https://pulp.plan.io/issues/5716>`_
- Remove the empty Migration page under installation. The migration tool will add this content back as
  it becomes available.
  `#5717 <https://pulp.plan.io/issues/5717>`_
- Removes the empty Distributed Installation page.
  `#5718 <https://pulp.plan.io/issues/5718>`_
- Extract the section "Settings" from the section "Configuration"
  `#5719 <https://pulp.plan.io/issues/5719>`_
- Adding dedicated `Rest API` left-navigation section.
  `#5722 <https://pulp.plan.io/issues/5722>`_
- Move `Client Bindings` to their own page and fix links.
  `#5723 <https://pulp.plan.io/issues/5723>`_
- Rearranged contributing documentation.
  `#5724 <https://pulp.plan.io/issues/5724>`_
- Removes the empty Troubleshooting page.
  `#5725 <https://pulp.plan.io/issues/5725>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Resource managers must now have the name ``resource-manager``. For example::

       /path/to/python/bin/rq worker -n 'resource-manager' -w 'pulpcore.tasking.worker.PulpWorker' -c 'pulpcore.rqconfig'
  `#3707 <https://pulp.plan.io/issues/3707>`_
- Remove "spawned_tasks" and "parent" field from tasks.
  `#5710 <https://pulp.plan.io/issues/5710>`_
- The ``/pulp/api/v3/status/`` had the ``missing_workers`` section removed. Also the
  ``online_workers`` key had the ``online`` and ``missing`` keys removed.
  `#5786 <https://pulp.plan.io/issues/5786>`_
- Remove Publishers from pulpcore

  Now that all plugins use Publications instead of Publishers,
  remove Publisher model from pulpcore.
  `#5814 <https://pulp.plan.io/issues/5814>`_


Misc
~~~~

- `#5777 <https://pulp.plan.io/issues/5777>`_


Plugin API
----------

Features
~~~~~~~~

- Added artifact path overlap checks for repo versions and publications. Plugin writers should call
  ``validate_version_paths()`` or ``validate_publication_paths()`` during the finalize step when
  creating RepositoryVersions or Publications (respectively).
  `#5559 <https://pulp.plan.io/issues/5559>`_
- Add a new ``finalize_new_publication()`` hook for plugin writers to call before a Publication is finalized.
  `#5827 <https://pulp.plan.io/issues/5827>`_


Bugfixes
~~~~~~~~

- Adds entries to all intended plugin API endpoints to import through ``pulpcore.plugin``. This allows
  all plugins to safely use the plugin API as long as they import from ``pulpcore.plugin``.
  `#5693 <https://pulp.plan.io/issues/5693>`_
- Fix the pulp_type field output in __str__ for MasterModels.
  `#5733 <https://pulp.plan.io/issues/5733>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- The ``pulpcore.plugin.models.Model`` is renamed to ``pulpcore.plugin.models.BaseModel``. Also the
  following objects have been removed from the plugin API:

  * ``pulpcore.plugin.serializers.NestedIdentityField``
  * ``pulpcore.plugin.serializers.SingleContentArtifactField``
  * ``pulpcore.plugin.serializers.relative_path_validator``
  * ``pulpcore.plugin.viewsets.RemoteFilter``
  `#5693 <https://pulp.plan.io/issues/5693>`_


----


3.0.0rc8 (2019-11-13)
=====================
REST API
--------

Features
~~~~~~~~

- New repository version is not created if no content was added or removed.
  `#3308 <https://pulp.plan.io/issues/3308>`_
- Change `relative_path` from `CharField` to `TextField`
  `#4544 <https://pulp.plan.io/issues/4544>`_
- Create Master/Detail models, serializers, viewsets for FileSystemExporter.
  `#5086 <https://pulp.plan.io/issues/5086>`_
- Adds ability to view content served by pulpcore-content in a browser.
  `#5378 <https://pulp.plan.io/issues/5378>`_
- Adds ability to view distributions served by pulpcore-content in a browser.
  `#5397 <https://pulp.plan.io/issues/5397>`_
- Users specify Pulp settings file locaiton and type using `PULP_SETTINGS` environment variable.
  `#5560 <https://pulp.plan.io/issues/5560>`_
- Added ``CONTENT_ORIGIN`` setting, which is now required.
  `#5629 <https://pulp.plan.io/issues/5629>`_
- Add storage information to the status API. Currently limited to disk space information.
  `#5631 <https://pulp.plan.io/issues/5631>`_


Bugfixes
~~~~~~~~

- Raise meaningful error for invalid filters.
  `#4780 <https://pulp.plan.io/issues/4780>`_
- Fix bug where 'ordering' parameter returned 400 error.
  `#5621 <https://pulp.plan.io/issues/5621>`_
- Handling `write_only` fields on OpenAPISchema.
  `#5622 <https://pulp.plan.io/issues/5622>`_
- Updated our package version requirements to be compatible with CentOS 7.
  `#5696 <https://pulp.plan.io/issues/5696>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Repository version number is no longer incremented if content has not changed.
  `#3308 <https://pulp.plan.io/issues/3308>`_
- The /pulp/api/v3/repositories/ endpoint has been removed and Repositories have made a "typed" object. They now live at /pulp/api/v3/repositories/<plugin>/<type>, e.g. /repositories/file/file/.

  The convention for sync is that it will now be performed by POSTing to {repo_href}/sync/ remote={remote_href} instead of by POSTING to {remote_href}/sync/ repository={repo_href}. The latter convention will break due to the aforementioned change.
  `#5625 <https://pulp.plan.io/issues/5625>`_
- Remove plugin managed repos
  `#5627 <https://pulp.plan.io/issues/5627>`_
- Removed CONTENT_HOST variable and replace its functionality with CONTENT_ORIGIN.
  `#5649 <https://pulp.plan.io/issues/5649>`_
- Renamed ssl_ca_certificate to ca_cert, ssl_client_certificate to client_cert, ssl_client_key to
  client_key, and ssl_validation to tls_validation.
  `#5695 <https://pulp.plan.io/issues/5695>`_


Misc
~~~~

- `#5028 <https://pulp.plan.io/issues/5028>`_, `#5353 <https://pulp.plan.io/issues/5353>`_, `#5574 <https://pulp.plan.io/issues/5574>`_, `#5580 <https://pulp.plan.io/issues/5580>`_, `#5609 <https://pulp.plan.io/issues/5609>`_, `#5612 <https://pulp.plan.io/issues/5612>`_, `#5686 <https://pulp.plan.io/issues/5686>`_


Plugin API
----------

Features
~~~~~~~~

- Added `Repository.finalize_new_version(new_version)` which is called by `RepositoryVersion.__exit__`
  to allow plugin-code to validate or modify the `RepositoryVersion` before pulpcore marks it as
  complete and saves it.

  Added `pulpcore.plugin.repo_version_utils.remove_duplicates(new_version)` for plugin writers to use.
  It relies on the definition of repository uniqueness from the `repo_key_fields` tuple plugins can
  define on their `Content` subclasses.
  `#3541 <https://pulp.plan.io/issues/3541>`_
- Create Master/Detail models, serializers, viewsets for FileSystemExporter.
  `#5086 <https://pulp.plan.io/issues/5086>`_
- Added the ``CONTENT_ORIGIN`` setting which can be used to reliably know the scheme+host+port to the
  pulp content app.
  `#5629 <https://pulp.plan.io/issues/5629>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Be more explicit about namespacing `ref_name` in plugin serializers.
  `#5574 <https://pulp.plan.io/issues/5574>`_
- Add `Plugin API` section to the changelog.
  `#5628 <https://pulp.plan.io/issues/5628>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Renamed the Content.repo_key to be Content.repo_key_fields. Also the calling of `remove_duplicates`
  no longer happens in `RepositoryVersion.add_content` and instead is intended for plugins to call
  from `Repository.finalize_new_version(new_version)`. Also the `pulpcore.plugin.RemoveDuplicates`
  Stage was removed.
  `#3541 <https://pulp.plan.io/issues/3541>`_
- models.RepositoryVersion.create() is no longer available, it has been replaced by {repository instance}.new_version().

  The convention for sync is that it will now be performed by POSTing to {repo_href}/sync/ remote={remote_href} instead of by POSTING to {remote_href}/sync/ repository={repo_href}. The latter will break due to becoming a typed resource, so plugins will need to adjust their code for the former convention.

  Make repositories "typed". Plugin writers need to subclass the Repository model, viewset, and serializer, as well as the RepositoryVersion viewset (just the viewset). They should also remove the /sync/ endpoint from their remote viewset and place it on the repository viewset.
  `#5625 <https://pulp.plan.io/issues/5625>`_
- Remove plugin managed repos
  `#5627 <https://pulp.plan.io/issues/5627>`_


----


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

- Adds an `authentication section <https://docs.pulpproject.org/installation/
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


