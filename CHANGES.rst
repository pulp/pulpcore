=========
Changelog
=========

..
    You should *NOT* be adding new change log entries to this file, this
    file is managed by towncrier. You *may* edit previous change logs to
    fix problems like typo corrections or such.
    To add a new change log entry, please see
    https://docs.pulpproject.org/contributing/git.html#changelog-update

    WARNING: Don't drop the towncrier directive!

.. warning::
    Until Role-Based Access Control is added to Pulp, REST API is not safe for multi-user use.
    Sensitive credentials can be read by any user, e.g. ``Remote.password``, ``Remote.client_key``.

.. towncrier release notes start

3.14.2 (2021-07-13)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed bug where content app would not respond to ``Range`` HTTP Header in requests when
  ``remote.policy`` was either ``on_demand`` or ``streamed``. For example this request is used by
  Anaconda clients.
  (backported from #8865)
  `#9057 <https://pulp.plan.io/issues/9057>`_
- Fixed a bug that caused a serializer to ignore form data for ``pulp_labels``.
  (backported from #8954)
  `#9058 <https://pulp.plan.io/issues/9058>`_
- Fixed the behavior of setting "repository" on a distribution for publication-based plugins.
  (backported from #9039)
  `#9059 <https://pulp.plan.io/issues/9059>`_
- Use proxy auth from Remote config to download content from a remote repository.
  (backported from #9024)
  `#9068 <https://pulp.plan.io/issues/9068>`_
- Fixed server error when accessing invalid files from content app base directory
  (backported from #9074)
  `#9077 <https://pulp.plan.io/issues/9077>`_


Misc
~~~~

- `#9063 <https://pulp.plan.io/issues/9063>`_


Plugin API
----------

No significant changes.


3.14.1 (2021-07-07)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a regression preventing syncs from file:// urls.
  (backported from #9003)
  `#9015 <https://pulp.plan.io/issues/9015>`_
- Removed ambiguity from the OpenAPI schema for Exports. The exported_resources are now a list of URI strings.
  (backported from #9008)
  `#9025 <https://pulp.plan.io/issues/9025>`_


Plugin API
----------

No significant changes.


3.14.0 (2021-07-01)
===================
REST API
--------

Features
~~~~~~~~

- Introduce new worker style. (tech-preview)
  `#8501 <https://pulp.plan.io/issues/8501>`_
- Added new endpoint ``/pulp/api/v3/orphans/cleanup/``. When called with ``POST`` and no parameters
  it is equivalent to calling ``DELETE /pulp/api/v3/orphans/``. Additionally the optional parameter
  ``content_hrefs`` can be specified and must contain a list of content hrefs. When ``content_hrefs``
  is specified, only those content units will be considered to be removed by orphan cleanup.
  `#8658 <https://pulp.plan.io/issues/8658>`_
- Content app responses are now smartly cached in Redis.
  `#8805 <https://pulp.plan.io/issues/8805>`_
- Downloads from remote sources will now be retried on more kinds of errors, such as HTTP 500 or socket errors.
  `#8881 <https://pulp.plan.io/issues/8881>`_
- Add a correlation id filter to the task list endpoint.
  `#8891 <https://pulp.plan.io/issues/8891>`_
- Where before ``download_concurrency`` would previously be set to a default value upon creation, it will now be set NULL (but a default value will still be used).
  `#8897 <https://pulp.plan.io/issues/8897>`_
- Added graceful shutdown to pulpcore workers.
  `#8930 <https://pulp.plan.io/issues/8930>`_
- Activate the new task worker type by default.

  .. warning::

     If you intend to stick with the old tasking system, you should configure the
     ``USE_NEW_WORKER_TYPE`` setting to false before upgrading.
  `#8948 <https://pulp.plan.io/issues/8948>`_


Bugfixes
~~~~~~~~

- Fixed race condition where a task could clean up reserved resources shared with another task.
  `#8637 <https://pulp.plan.io/issues/8637>`_
- Altered redirect URL escaping, preventing invalidation of signed URLs for artifacts using cloud storage.
  `#8670 <https://pulp.plan.io/issues/8670>`_
- Add an update row lock on in task dispatching for ``ReservedResource`` to prevent a race where an
  object was deleted that was supposed to be reused. This prevents a condition where tasks ended up in
  waiting state forever.
  `#8708 <https://pulp.plan.io/issues/8708>`_
- Retry downloads on ``ClientConnectorSSLError``, which appears to be spuriously returned by some CDNs.
  `#8867 <https://pulp.plan.io/issues/8867>`_
- Fixed OpenAPI schema tag generation for resources that are nested more than 2 levels.

  This change is most evident in client libraries generated from the OpenAPI schema.

  Prior to this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` was named `ExportersCoreExportsApi`.

  After this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` is named `ExportersPulpExportsApi`.
  `#8868 <https://pulp.plan.io/issues/8868>`_
- Fixed request schema for ``/pulp/api/v3/repair/``, which did identify any arguments. This also fixes
  the bindings.
  `#8869 <https://pulp.plan.io/issues/8869>`_
- Update default access policies in the database if they were unmodified by the administrator.
  `#8883 <https://pulp.plan.io/issues/8883>`_
- Pinning to psycopg2 < 2.9 as psycopg 2.9 doesn't work with django 2.2. More info at
  https://github.com/django/django/commit/837ffcfa681d0f65f444d881ee3d69aec23770be.
  `#8926 <https://pulp.plan.io/issues/8926>`_
- Fixed bug where artifacts and content were not always saved in Pulp with each
  on_demand request serviced by content app.
  `#8980 <https://pulp.plan.io/issues/8980>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Fixed a number of link-problems in the installation/ section of docs.
  `#6837 <https://pulp.plan.io/issues/6837>`_
- Added a troubleshooting section to the docs explaining how to find stuck tasks.
  `#8774 <https://pulp.plan.io/issues/8774>`_
- Moved existing basic auth docs to a new top-level section named Authentication.
  `#8800 <https://pulp.plan.io/issues/8800>`_
- Moved ``Webserver Authentication`` docs under the top-level ``Authentication`` section.
  `#8801 <https://pulp.plan.io/issues/8801>`_
- Provide instructions to use Keycloak authenication using Python Social Aauth
  `#8803 <https://pulp.plan.io/issues/8803>`_
- Updated the docs.pulpproject.org to provide some immediate direction for better user orientation.
  `#8946 <https://pulp.plan.io/issues/8946>`_
- Separated hardware and Filesystem information from the Architecture section and added them to the Installation section.
  `#8947 <https://pulp.plan.io/issues/8947>`_
- Added sub-headings and simplified language of Pulp concept section.
  `#8949 <https://pulp.plan.io/issues/8949>`_


Deprecations
~~~~~~~~~~~~

- Deprecated the ``DELETE /pulp/api/v3/orphans/`` call. Instead use the
  ``POST /pulp/api/v3/orphans/cleanup/`` call.
  `#8876 <https://pulp.plan.io/issues/8876>`_


Misc
~~~~

- `#8821 <https://pulp.plan.io/issues/8821>`_, `#8827 <https://pulp.plan.io/issues/8827>`_, `#8975 <https://pulp.plan.io/issues/8975>`_


Plugin API
----------

Features
~~~~~~~~

- Added the ``pulpcore.plugin.viewsets.DistributionFilter``. This should be used instead of
  ``pulpcore.plugin.viewsets.NewDistributionFilter``.
  `#8480 <https://pulp.plan.io/issues/8480>`_
- Added ``user_hidden`` field to ``Repository`` to hide repositories from users.
  `#8487 <https://pulp.plan.io/issues/8487>`_
- Added a ``timestamp_of_interest`` field to Content and Artifacts. This field can be updated by
  calling a new method ``touch()`` on Artifacts and Content. Plugin writers should call this method
  whenever they deal with Content or Artifacts. For example, this includes places where Content is
  uploaded or added to Repository Versions. This will prevent Content and Artifacts from being cleaned
  up when orphan cleanup becomes a non-blocking task in pulpcore 3.15.
  `#8823 <https://pulp.plan.io/issues/8823>`_
- Exposed ``AsyncUpdateMixin`` through ``pulpcore.plugin.viewsets``.
  `#8844 <https://pulp.plan.io/issues/8844>`_
- Added a field ``DEFAULT_MAX_RETRIES`` to the ``Remote`` base class - plugin writers can override the default number of retries attempted when file downloads failed for each type of remote. The default value is 3.
  `#8881 <https://pulp.plan.io/issues/8881>`_
- Added a field ``DEFAULT_DOWNLOAD_CONCURRENCY`` to the Remote base class - plugin writers can override the number of concurrent downloads for each type of remote. The default value is 10.
  `#8897 <https://pulp.plan.io/issues/8897>`_


Bugfixes
~~~~~~~~

- Fixed OpenAPI schema tag generation for resources that are nested more than 2 levels.

  This change is most evident in client libraries generated from the OpenAPI schema.

  Prior to this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` was named `ExportersCoreExportsApi`.

  After this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` is named `ExportersPulpExportsApi`.
  `#8868 <https://pulp.plan.io/issues/8868>`_


Removals
~~~~~~~~

- The usage of non-JSON serializable types of ``args`` and ``kwargs`` to tasks is no longer supported.
  ``uuid.UUID`` objects however will silently be converted to ``str``.
  `#8501 <https://pulp.plan.io/issues/8501>`_
- Removed the ``versions_containing_content`` method from the
  `pulpcore.plugin.models.RepositoryVersion`` object. Instead use
  ``RepositoryVersion.objects.with_content()``.
  `#8729 <https://pulp.plan.io/issues/8729>`_
- Removed `pulpcore.plugin.stages.ContentUnassociation` from the plugin API.
  `#8827 <https://pulp.plan.io/issues/8827>`_


Deprecations
~~~~~~~~~~~~

- The ``pulpcore.plugin.viewsets.NewDistributionFilter`` is deprecated and will be removed from a
  future release. Instead use ``pulpcore.plugin.viewsets.DistributionFilter``.
  `#8480 <https://pulp.plan.io/issues/8480>`_
- Deprecate the use of the `reserved_resources_record__resource` in favor of `reserved_resources_record__contains`.
  Tentative removal release is pulpcore==3.15.
  `#8501 <https://pulp.plan.io/issues/8501>`_
- Plugin writers who create custom downloaders by subclassing ``HttpDownloader`` no longer need to wrap the ``_run()`` method with a ``backoff`` decorator. Consequntly the ``http_giveup`` handler the sake of the ``backoff`` decorator is no longer needed and has been deprecated. It is likely to be removed in pulpcore 3.15.
  `#8881 <https://pulp.plan.io/issues/8881>`_


3.13.0 (2021-05-25)
===================
REST API
--------

Features
~~~~~~~~

- Added two views to identify content which belongs to repository_version or publication.
  `#4832 <https://pulp.plan.io/issues/4832>`_
- Added repository field to repository version endpoints.
  `#6068 <https://pulp.plan.io/issues/6068>`_
- Added ability for users to limit how many repo versions Pulp retains by setting
  ``retained_versions`` on repository.
  `#8368 <https://pulp.plan.io/issues/8368>`_
- Added the ``add-signing-service`` management command.
  Notice that it is still in tech-preview and can change without further notice.
  `#8609 <https://pulp.plan.io/issues/8609>`_
- Added a ``pulpcore-worker`` entrypoint to simplify and unify the worker command.
  `#8721 <https://pulp.plan.io/issues/8721>`_
- Content app auto-distributes latest publication if distribution's ``repository`` field is set
  `#8760 <https://pulp.plan.io/issues/8760>`_


Bugfixes
~~~~~~~~

- Fixed cleanup of UploadChunks when their corresponding Upload is deleted.
  `#7316 <https://pulp.plan.io/issues/7316>`_
- Fixed an issue that caused the request's context to be ignored in the serializers.
  `#8396 <https://pulp.plan.io/issues/8396>`_
- Fixed missing ``REDIS_SSL`` parameter in RQ config.
  `#8525 <https://pulp.plan.io/issues/8525>`_
- Fixed bug where using forms submissions to create resources (e.g. ``Remotes``) raised exception
  about the format of ``pulp_labels``.
  `#8541 <https://pulp.plan.io/issues/8541>`_
- Fixed bug where publications sometimes fail with the error '[Errno 39] Directory not empty'.
  `#8595 <https://pulp.plan.io/issues/8595>`_
- Handled a tasking race condition where cleaning up resource reservations sometimes raised an IntegrityError.
  `#8603 <https://pulp.plan.io/issues/8603>`_
- Fixed on-demand sync/migration of repositories that don't have sha256 checksums.
  `#8625 <https://pulp.plan.io/issues/8625>`_
- Taught pulp-export to validate chunk-size to be <= 1TB.
  `#8628 <https://pulp.plan.io/issues/8628>`_
- Addressed a race-condition in PulpImport that could fail with unique-constraint violations.
  `#8633 <https://pulp.plan.io/issues/8633>`_
- Content app now properly lists all distributions present
  `#8636 <https://pulp.plan.io/issues/8636>`_
- Fixed ability to specify custom headers on a Remote.
  `#8689 <https://pulp.plan.io/issues/8689>`_
- Fixed compatibility with Django 2.2 LTS. Pulp now requires Django~=2.2.23
  `#8691 <https://pulp.plan.io/issues/8691>`_
- Skip allowed content checks on collectstatic
  `#8711 <https://pulp.plan.io/issues/8711>`_
- Fixed a bug in the retained versions code where content wasn't being properly moved to newer repo
  versions when old versions were cleaned up.
  `#8793 <https://pulp.plan.io/issues/8793>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added docs on how to list the effective settings using ``dynaconf list``.
  `#6235 <https://pulp.plan.io/issues/6235>`_
- Added anti-instructions, that users should never run `pulpcore-manager makemigrations``, but file a bug instead.
  `#6703 <https://pulp.plan.io/issues/6703>`_
- Clarified repositories are typed in concepts page
  `#6990 <https://pulp.plan.io/issues/6990>`_
- Added UTF-8 character set encoding as a requirement for PostgreSQL
  `#7019 <https://pulp.plan.io/issues/7019>`_
- Fixed typo s/comtrol/control
  `#7715 <https://pulp.plan.io/issues/7715>`_
- Removed the PUP references from the docs.
  `#7747 <https://pulp.plan.io/issues/7747>`_
- Updated plugin writers' guide to not use settings directly in the model fields.
  `#7776 <https://pulp.plan.io/issues/7776>`_
- Make the reference to the Pulp installer documentation more explicit.
  `#8477 <https://pulp.plan.io/issues/8477>`_
- Removed example Ansible installer playbook from the pulpcore docs so that Pulp users would have a single source of truth in the pulp-installer docs.
  `#8550 <https://pulp.plan.io/issues/8550>`_
- Added security disclosures ref to homepage
  `#8584 <https://pulp.plan.io/issues/8584>`_
- Add sequential steps for storage docs
  `#8597 <https://pulp.plan.io/issues/8597>`_
- Updated signing service workflow. Removed old deprecation warning.
  `#8609 <https://pulp.plan.io/issues/8609>`_
- Add an example of how to specify an array value and a dict key in the auth methods section
  `#8668 <https://pulp.plan.io/issues/8668>`_
- Fixed docs build errors reported by autodoc.
  `#8784 <https://pulp.plan.io/issues/8784>`_


Misc
~~~~

- `#8524 <https://pulp.plan.io/issues/8524>`_, `#8656 <https://pulp.plan.io/issues/8656>`_, `#8761 <https://pulp.plan.io/issues/8761>`_


Plugin API
----------

Features
~~~~~~~~

- Undeprecated the use of ``uuid.UUID`` in task arguments. With this, primary keys do not need to be explicitely cast to ``str``.
  `#8723 <https://pulp.plan.io/issues/8723>`_


Bugfixes
~~~~~~~~

- Added RepositoryVersionRelatedField to the plugin API.
  `#8578 <https://pulp.plan.io/issues/8578>`_
- Fixed auto-distribute w/ retained_versions tests
  `#8792 <https://pulp.plan.io/issues/8792>`_


Removals
~~~~~~~~

- Removed deprecated ``pulpcore.plugin.tasking.WorkingDirectory``.
  `#8354 <https://pulp.plan.io/issues/8354>`_
- Removed ``BaseDistribution``, ``PublicationDistribution``, and ``RepositoryVersionDistribution``
  models. Removed ``BaseDistributionSerializer``, ``PublicationDistributionSerializer``, and
  ``RepositoryVersionDistributionSerializer`` serializers. Removed ``BaseDistributionViewSet`` and
  ``DistributionFilter``.
  `#8386 <https://pulp.plan.io/issues/8386>`_
- Removed ``pulpcore.plugin.tasking.enqueue_with_reservation``.
  `#8497 <https://pulp.plan.io/issues/8497>`_


Deprecations
~~~~~~~~~~~~

- RepositoryVersion method "versions_containing_content" is deprecated now.
  `#4832 <https://pulp.plan.io/issues/4832>`_
- The usage of the `pulpcore.plugin.stages.ContentUnassociation` stage has been deprecated. A future update will remove it from the plugin API.
  `#8635 <https://pulp.plan.io/issues/8635>`_


3.12.2 (2021-04-29)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Backported a fix for on-demand sync/migration of repositories that don't have sha256 checksums.
  `#8652 <https://pulp.plan.io/issues/8652>`_


Plugin API
----------

No significant changes.


3.12.1 (2021-04-20)
===================
REST API
--------

No significant changes.


Plugin API
----------

Bugfixes
~~~~~~~~

- Added RepositoryVersionRelatedField to the plugin API.
  `#8580 <https://pulp.plan.io/issues/8580>`_


3.12.0 (2021-04-08)
===================
REST API
--------

Features
~~~~~~~~

- Add support for automatic publishing and distributing.
  `#7626 <https://pulp.plan.io/issues/7626>`_
- Add a warning at startup time if there are remote artifacts with checksums but no allowed checksums.
  `#7985 <https://pulp.plan.io/issues/7985>`_
- Added support in content app for properly handling unknown or forbidden digest errors.
  `#7989 <https://pulp.plan.io/issues/7989>`_
- Added sync check that raises error when only forbidden checksums are found for on-demand content.
  `#8423 <https://pulp.plan.io/issues/8423>`_
- Added ability for users to delete repo version 0 as long as they still have at least one repo
  version for their repo.
  `#8454 <https://pulp.plan.io/issues/8454>`_


Bugfixes
~~~~~~~~

- Added asynchronous tasking to the Update and Delete endpoints of PulpExporter to provide proper locking on resources.
  `#7438 <https://pulp.plan.io/issues/7438>`_
- Fixed a scenario where canceled tasks could be marked failed.
  `#7980 <https://pulp.plan.io/issues/7980>`_
- Taught ``PulpImport`` correct way to find and import ``RepositoryVersions``. Previous
  implementation only worked for ``RepositoryVersions`` that were the 'current' version
  of the exported ``Repository``.
  `#8116 <https://pulp.plan.io/issues/8116>`_
- Fixed a race condition that sometimes surfaced during handling of reserved resources.
  `#8352 <https://pulp.plan.io/issues/8352>`_
- Made digest and size sync erros more helpful by logging url of the requested files.
  `#8357 <https://pulp.plan.io/issues/8357>`_
- Fixed artifact-stage to handle an edge-case when multiple multi-artifact content, from different remotes, is in a single batch.
  `#8377 <https://pulp.plan.io/issues/8377>`_
- Fixed Azure artifacts download.
  `#8427 <https://pulp.plan.io/issues/8427>`_
- Fixed bug during sync where a unique constraint violation for ``Content`` would raise an "X matching
  query does not exist" error.
  `#8430 <https://pulp.plan.io/issues/8430>`_
- Fix artifact checksum check to not check on-demand content.
  `#8445 <https://pulp.plan.io/issues/8445>`_
- Fixed a bug where the existence of PublishedMetadata caused ``LookupError`` when querying ``/pulp/api/v3/content/``
  `#8447 <https://pulp.plan.io/issues/8447>`_
- Distributions are now viewable again at the base url of the content app
  `#8475 <https://pulp.plan.io/issues/8475>`_
- Fixed a path in artifact_stages that could lead to sync-failures in pulp_container.
  `#8489 <https://pulp.plan.io/issues/8489>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Update docs with guide how to change 'ALLOWED_CONTENT_CHECKSUMS' setting using 'pulpcore-manager handle-artifact-checksums --report' if needed.
  `#8325 <https://pulp.plan.io/issues/8325>`_


Removals
~~~~~~~~

- The Update and Delete endpoints of Exporters changed to now return 202 with tasks.
  `#7438 <https://pulp.plan.io/issues/7438>`_
- Deprecation warnings are now being logged by default if the log level includes WARNING. This can be
  disabled by adjusting the log level of ``pulpcore.deprecation``. See the deprecation docs for more
  information.
  `#8499 <https://pulp.plan.io/issues/8499>`_


Misc
~~~~

- `#8450 <https://pulp.plan.io/issues/8450>`_


Plugin API
----------

Features
~~~~~~~~

- Added a new callback method to ``Repository`` named ``on_new_version()``, which runs when a new repository version has been created. This can be used for e.g. automatically publishing or distributing a new repository version after it has been created.
  `#7626 <https://pulp.plan.io/issues/7626>`_
- Added url as optional argument to ``DigestValidationError`` and ``SizeValidationError`` exceptions to log urls in the exception message.
  `#8357 <https://pulp.plan.io/issues/8357>`_
- Added the following new objects related to a new ``Distribution`` MasterModel:
  * ``pulpcore.plugin.models.Distribution`` - A new MasterModel ``Distribution`` which replaces the
    ``pulpcore.plugin.models.BaseDistribution``. This now contains the ``repository``,
    ``repository_version``, and ``publication`` fields on the MasterModel instead of on the detail
    models as was done with ``pulpcore.plugin.models.BaseDistribution``.
  * ``pulpcore.plugin.serializer.DistributionSerializer`` - A serializer plugin writers should use
    with the new ``pulpcore.plugin.models.Distribution``.
  * ``pulpcore.plugin.viewset.DistributionViewSet`` - The viewset that replaces the deprecated
    ``pulpcore.plugin.viewset.BaseDistributionViewSet``.
  * ``pulpcore.plugin.viewset.NewDistributionFilter`` - The filter that pairs with the
    ``Distribution`` model.
  `#8384 <https://pulp.plan.io/issues/8384>`_
- Added checksum type enforcement to ``pulpcore.plugin.download.BaseDownloader``.
  `#8435 <https://pulp.plan.io/issues/8435>`_
- Adds the ``pulpcore.plugin.tasking.dispatch`` interface which replaces the
  ``pulpcore.plugin.tasking.enqueue_with_reservation`` interface. It is the same except:
  * It returns a ``pulpcore.plugin.models.Task`` instead of an RQ object
  * It does not support the ``options`` keyword argument

  Additionally the ``pulpcore.plugin.viewsets.OperationPostponedResponse`` was updated to support both
  the ``dispatch`` and ``enqueue_with_reservation`` interfaces.
  `#8496 <https://pulp.plan.io/issues/8496>`_


Bugfixes
~~~~~~~~

- Allow plugins to unset the ``queryset_filtering_required_permission`` attribute in ``NamedModelViewSet``.
  `#8438 <https://pulp.plan.io/issues/8438>`_


Removals
~~~~~~~~

- Removed checksum type filtering from ``pulpcore.plugin.models.Remote.get_downloader`` and ``pulpcore.plugin.stages.DeclarativeArtifact.download``.
  `#8435 <https://pulp.plan.io/issues/8435>`_


Deprecations
~~~~~~~~~~~~

- The following objects were deprecated:
  * ``pulpcore.plugin.models.BaseDistribution`` -- Instead use
    ``pulpcore.plugin.models.Distribution``.
  * ``pulpcore.plugin.viewset.BaseDistributionViewSet`` -- Instead use
    ``pulpcore.plugin.viewset.DistributionViewSet``.
  * ``pulpcore.plugin.serializer.BaseDistributionSerializer`` -- Instead use
    ``pulpcore.plugin.serializer.DistributionSerializer``.
  * ``pulpcore.plugin.serializer.PublicationDistributionSerializer`` -- Instead use define the
    ``publication`` field directly on your detail distribution object. See the docstring for
    ``pulpcore.plugin.serializer.DistributionSerializer`` for an example.
  * ``pulpcore.plugin.serializer.RepositoryVersionDistributionSerializer`` -- Instead use define the
    ``repository_version`` field directly on your detail distribution object. See the docstring for
    ``pulpcore.plugin.serializer.DistributionSerializer`` for an example.
  * ``pulpcore.plugin.viewset.DistributionFilter`` -- Instead use
    ``pulpcore.plugin.viewset.NewDistributionFilter``.

  .. note::

      You will have to define a migration to move your data from
      ``pulpcore.plugin.models.BaseDistribution`` to ``pulpcore.plugin.models.Distribution``. See the
      pulp_file migration 0009 as a reference example.
  `#8385 <https://pulp.plan.io/issues/8385>`_
- Deprecated the ``pulpcore.plugin.tasking.enqueue_with_reservation``. Instead use the
  ``pulpcore.plugin.tasking.dispatch`` interface.
  `#8496 <https://pulp.plan.io/issues/8496>`_
- The usage of non-JSON serializable types of ``args`` and ``kwargs`` to tasks is deprecated. Future
  releases of pulpcore may discontinue accepting complex argument types. Note, UUID objects are not
  JSON serializable. A deprecated warning is logged if a non-JSON serializable is used.
  `#8505 <https://pulp.plan.io/issues/8505>`_


3.11.2 (2021-05-25)REST API
--------

Bugfixes
~~~~~~~~

- Skip allowed content checks on collectstatic
  (backported from #8711)
  `#8712 <https://pulp.plan.io/issues/8712>`_
- Fixed cleanup of UploadChunks when their corresponding Upload is deleted.
  (backported from #7316)
  `#8757 <https://pulp.plan.io/issues/8757>`_
- Fixed compatibility with Django 2.2 LTS. Pulp now requires Django~=2.2.23
  (backported from #8691)
  `#8758 <https://pulp.plan.io/issues/8758>`_
- Pinned click~=7.1.2 to ensure RQ is compatible with it.
  `#8767 <https://pulp.plan.io/issues/8767>`_


Plugin API
----------

No significant changes.


3.11.1 (2021-04-29)
===================
REST API
--------

Bugfixes
~~~~~~~

- Fixed a race condition that sometimes surfaced during handling of reserved resources.
  `#8632 <https://pulp.plan.io/issues/8632>`_
- Handled a tasking race condition where cleaning up resource reservations sometimes raised an IntegrityError.
  `#8648 <https://pulp.plan.io/issues/8648>`_


Plugin API
----------

Bugfixes
~~~~~~~

- Allow plugins to unset the ``queryset_filtering_required_permission`` attribute in ``NamedModelViewSet``.
  `#8444 <https://pulp.plan.io/issues/8444>`_


3.11.0 (2021-03-15)
===================
REST API
--------

Features
~~~~~~~~

- Raise error when syncing content with a checksum not included in ``ALLOWED_CONTENT_CHECKSUMS``.
  `#7854 <https://pulp.plan.io/issues/7854>`_
- User can evaluate how many content units are affected with checksum type change with 'pulpcore-manager handle-artifact-checksums --report'.
  `#7986 <https://pulp.plan.io/issues/7986>`_
- The fields ``proxy_username`` and ``proxy_password`` have been added to remotes.
  Credentials can no longer be specified as part of the ``proxy_url``.
  A data migration will move the proxy auth information on existing remotes to the new fields.
  `#8167 <https://pulp.plan.io/issues/8167>`_
- Added the ``WORKER_TTL`` setting, that specifies the interval a worker is considered missing after its last heartbeat.
  `#8291 <https://pulp.plan.io/issues/8291>`_
- Due to the removal of ``md5`` and ``sha1`` from the ``ALLOWED_CONTENT_CHECKSUMS`` setting, every
  system that had any Artifacts synced in in prior to 3.11 will have to run the ``pulpcore-manager
  handle-content-checksums`` command. A data migration is provided with 3.11 that will run this
  automatically as part of the ``pulpcore-manager migrate`` command all upgrades must run anyway.
  `#8322 <https://pulp.plan.io/issues/8322>`_


Bugfixes
~~~~~~~~

- Fixed a bug experienced by the migration plugin where all content objects are assumed to have a
  remote associated with them.
  `#7876 <https://pulp.plan.io/issues/7876>`_
- Restored inadvertently-changed content-guards API to its correct endpoint.

  In the process of adding generic list-endpoints, the /pulp/api/v3/contentguards
  API was inadvertently rehomed to /pulp/api/v3/content_guards. This change restores
  it to its published value.
  `#8283 <https://pulp.plan.io/issues/8283>`_
- Added headers field to the list of fields in the ``RemoteSerializer`` base class and marked it optional to make it accessible via the REST api.
  `#8330 <https://pulp.plan.io/issues/8330>`_
- Fixed AccessPolicy AttributeError.
  `#8395 <https://pulp.plan.io/issues/8395>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Removed correlation id feature from tech preview.
  `#7927 <https://pulp.plan.io/issues/7927>`_
- Removed 'tech preview' label from ``handle-artifact-checksums`` command.

  ``handle-artifact-checksums`` is now a fully-supported part of Pulp3.
  `#7928 <https://pulp.plan.io/issues/7928>`_
- Added a warning banner to the ``ALLOWED_CONTENT_CHECKSUMS`` setting section indicating the setting
  is not fully enforcing in ``pulpcore`` code and various plugins.
  `#8342 <https://pulp.plan.io/issues/8342>`_


Removals
~~~~~~~~

- The ``component`` field of the ``versions`` section of the status API ```/pulp/api/v3/status/`` now
  lists the Django app name, not the Python package name. Similarly the OpenAPI schema at
  ``/pulp/api/v3`` does also.
  `#8198 <https://pulp.plan.io/issues/8198>`_
- Removed sensitive fields ``username``, ``password``, and ``client_key`` from Remote responses. These
  fields can still be set and updated but will no longer be readable.
  `#8202 <https://pulp.plan.io/issues/8202>`_
- Adjusted the ``ALLOWED_CONTENT_CHECKSUMS`` setting to remove ``md5`` and ``sha1`` since they are
  insecure. Now, by default, the ``ALLOWED_CONTENT_CHECKSUMS`` contain ``sha224``, ``sha256``,
  ``sha384``, and ``sha512``.
  `#8246 <https://pulp.plan.io/issues/8246>`_


Misc
~~~~

- `#7797 <https://pulp.plan.io/issues/7797>`_, `#7984 <https://pulp.plan.io/issues/7984>`_, `#8315 <https://pulp.plan.io/issues/8315>`_


Plugin API
----------

Features
~~~~~~~~

- Allow developers to use more than one WorkingDirectory() within a task, including nested calls. Tasks will also now use a temporary working directory by default.
  `#7815 <https://pulp.plan.io/issues/7815>`_
- Added the ``pulpcore.app.pulp_hashlib`` module which provides the ``new`` function and ensures only
  allowed hashers listed in ``ALLOWED_CONTENT_CHECKSUMS`` can be instantiated. Plugin writers should
  use this instead of ``hashlib.new`` to generate checksum hashers.
  `#7984 <https://pulp.plan.io/issues/7984>`_
- Add a ``get_content`` method to ``pulpcore.plugin.models.RepositoryVersion`` that accepts a
  queryset and returns a list of content in that repository using the given queryset.
  This allows for specific content type to be returned by executing
  ``repo_version.get_content(content_qs=MyContentType.objects)``.
  `#8375 <https://pulp.plan.io/issues/8375>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added docs identifying plugin writers to use the ``pulpcore.app.pulp_hashlib`` module which provides
  the ``new`` function and ensures only allowed hashers can be instantiated. This should be used in
  place of ``hashlib.new``.
  `#7984 <https://pulp.plan.io/issues/7984>`_
- The use of ``tempdir.TemporaryDirectory`` in tasks has been documented.
  `#8231 <https://pulp.plan.io/issues/8231>`_


Removals
~~~~~~~~

- Adjusted the ``ALLOWED_CONTENT_CHECKSUMS`` setting to remove ``md5`` and ``sha1`` since they are
  insecure. Now, by default, the ``ALLOWED_CONTENT_CHECKSUMS`` contain ``sha224``, ``sha256``,
  ``sha384``, and ``sha512``.
  `#8246 <https://pulp.plan.io/issues/8246>`_
- Removed unused `get_plugin_storage_path` method.
  `#8343 <https://pulp.plan.io/issues/8343>`_
- It is not longer possible to address AccessPolicy via the viewset's classname. Viewset's urlpattern should be used instead.
  `#8397 <https://pulp.plan.io/issues/8397>`_
- Removed deprecated `key` field returned by the signing service.
  Plugin writers must now refer directly to the `public_key` field on the signing service object.
  `#8398 <https://pulp.plan.io/issues/8398>`_


Deprecations
~~~~~~~~~~~~

- ``pulpcore.plugin.tasking.WorkingDirectory`` has been deprecated.
  `#8231 <https://pulp.plan.io/issues/8231>`_


3.10.0 (2021-02-04)
===================
REST API
--------

Features
~~~~~~~~

- Change the default deployment layout

  This changes the default deployment layout. The main change is that MEDIA_ROOT gets its own
  directory. This allows limiting the file permissions in a shared Pulp 2 + Pulp 3 deployment and the
  SELinux file contexts. Another benefit is compatibility with django_extensions' unreferenced_files
  command which lists all files in MEDIA_ROOT that are not in the database.

  Other paths are kept on the same absolute paths. The documentation is updated to show the latest
  best practices.
  `#7178 <https://pulp.plan.io/issues/7178>`_
- Added general endpoints to list ``Content``, ``ContentGuards``, and ``Repositories``.
  `#7204 <https://pulp.plan.io/issues/7204>`_
- Added /importers/core/pulp/import-check/ to validate import-parameters.
  `#7549 <https://pulp.plan.io/issues/7549>`_
- Added a new field called public_key to SigningService. This field preserves the value of the public
  key. In addition to that, the field fingerprint was introduced as well. This field identifies the
  public key.
  `#7700 <https://pulp.plan.io/issues/7700>`_
- Added possibility to filter users and groups by various fields.
  `#7975 <https://pulp.plan.io/issues/7975>`_
- Added pulp_labels to allow users to add key/value data to objects.
  `#8065 <https://pulp.plan.io/issues/8065>`_
- Added ``pulp_label_select`` filter to allow users to filter by labels.
  `#8067 <https://pulp.plan.io/issues/8067>`_
- Added optional headers field to the aiohttp ClientSession.
  `#8083 <https://pulp.plan.io/issues/8083>`_
- Allow querying names on the api using name__icontains, name__contains and name__startswith query parameters.
  `#8094 <https://pulp.plan.io/issues/8094>`_
- Added RBAC to the endpoint for managing groups.
  `#8159 <https://pulp.plan.io/issues/8159>`_
- Added RBAC to the endpoint for managing group users.
  `#8160 <https://pulp.plan.io/issues/8160>`_
- Added the ``AccessPolicy.customized`` field which if ``True`` indicates a user has modified the
  default AccessPolicy.
  `#8182 <https://pulp.plan.io/issues/8182>`_
- Added filtering for access policies.
  `#8189 <https://pulp.plan.io/issues/8189>`_
- As an authenticated user I can create and view artifacts.
  `#8193 <https://pulp.plan.io/issues/8193>`_


Bugfixes
~~~~~~~~

- Fixed bug where duplicate artifact error message was nondeterministic in displaying different error
  messages with different checksum types. Also, updated duplicate artifact error message to be more
  descriptive.
  `#3387 <https://pulp.plan.io/issues/3387>`_
- Fixed Pulp import/export bug that occurs when sha384 or sha512 is not in ``ALLOWED_CONTENT_CHECKSUMS``.
  `#7836 <https://pulp.plan.io/issues/7836>`_
- X-CSRFToken is not sent through ajax requests (PUT) in api.html. Fixed by setting the right value in
  the JS code.
  `#7888 <https://pulp.plan.io/issues/7888>`_
- Provide a mechanism to automatically resolve issues and prevent deadlocks when Redis experiences data loss (such as a restart).
  `#7912 <https://pulp.plan.io/issues/7912>`_
- Silence unnecessary log messages from django_guid which were spamming up the logs.
  `#7982 <https://pulp.plan.io/issues/7982>`_
- Changed the default permission class to ``IsAdminUser`` to protect endpoints not yet guarded by an access policy from users without permission.
  `#8018 <https://pulp.plan.io/issues/8018>`_
- Fixed apidoc bug, where model and object permissions on groups overlapped.
  `#8033 <https://pulp.plan.io/issues/8033>`_
- Fixed the viewset_name used by access policy for the cases when parent_viewset is involved.
  `#8152 <https://pulp.plan.io/issues/8152>`_
- Made the viewset_name property of access policies read only.
  `#8185 <https://pulp.plan.io/issues/8185>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added a description of the common filesystem layout in the deployment section.
  `#7750 <https://pulp.plan.io/issues/7750>`_
- Updated the reference to the new location of pulplift at the installer repository in the development section.
  `#7878 <https://pulp.plan.io/issues/7878>`_
- Add links to plugin docs into docs.pulpproject.org.
  `#8131 <https://pulp.plan.io/issues/8131>`_
- Added documentation for labels.
  `#8157 <https://pulp.plan.io/issues/8157>`_


Misc
~~~~

- `#8203 <https://pulp.plan.io/issues/8203>`_


Plugin API
----------

Features
~~~~~~~~

- Add ``rate_limit`` option to ``Remote``
  `#7965 <https://pulp.plan.io/issues/7965>`_
- Made DistributionFilter accessible to plugin writers.
  `#8059 <https://pulp.plan.io/issues/8059>`_
- Adding ``Label`` and ``LabelSerializer`` to the plugin api.
  `#8065 <https://pulp.plan.io/issues/8065>`_
- Added ``LabelSelectFilter`` to filter resources by labels.
  `#8067 <https://pulp.plan.io/issues/8067>`_
- Added ReadOnlyRepositoryViewset to the plugin API.
  `#8103 <https://pulp.plan.io/issues/8103>`_
- Added NAME_FILTER_OPTIONS to the plugin API to gain more consistency across plugins when filter by name or similar CharFields.
  `#8117 <https://pulp.plan.io/issues/8117>`_
- Added `has_repo_attr_obj_perms` and `has_repo_attr_model_or_obj_perms` to the global access checks available to all plugins to use.
  `#8161 <https://pulp.plan.io/issues/8161>`_


Removals
~~~~~~~~

- Plugins are required to define a ``version`` attribute on their subclass of
  ``PulpPluginAppConfig``. Starting with pulpcore==3.10, if undefined while Pulp loads, Pulp will
  refuse to start.
  `#7930 <https://pulp.plan.io/issues/7930>`_
- Changed the default permission class to from ``IsAuthenticated`` to ``IsAdminUser``.
  Any endpoints that should be accessible by all known to the system users need to specify the permission_classes accordingly.
  `#8018 <https://pulp.plan.io/issues/8018>`_
- ``pulpcore.plugin.models.UnsupportedDigestValidationError`` has been removed. Plugins should
  look for this at ``pulpcore.plugin.exceptions.UnsupportedDigestValidationError`` instead.
  `#8169 <https://pulp.plan.io/issues/8169>`_


Deprecations
~~~~~~~~~~~~

- Access to the path of the public key of a signing service was deprecated. The value of the public
  key is now expected to be saved in the model instance as ``SigningService.public_key``.
  `#7700 <https://pulp.plan.io/issues/7700>`_
- The ``pulpcore.plugin.storage.get_plugin_storage_path()`` method has been deprecated.
  `#7935 <https://pulp.plan.io/issues/7935>`_


3.9.1 (2021-01-21)
==================
REST API
--------

Removals
~~~~~~~~

- CHUNKED_UPLOAD_DIR was converted to a relative path inside MEDIA_ROOT.
  `#8099 <https://pulp.plan.io/issues/8099>`_

Plugin API
----------

No significant changes.


3.9.0 (2020-12-07)
==================
REST API
--------

Features
~~~~~~~~

- Made uploaded chunks to be stored as separate files in the default storage. This feature removes
  the need for a share storage of pulp api nodes, as the chunks are now stored individually in the
  shared storage and are therefore accessible by all nodes.
  `#4498 <https://pulp.plan.io/issues/4498>`_
- Add support for logging messages with a correlation id that can either be autogenerated or passed in
  with a ``Correlation-ID`` header. This feature is provided as a tech preview in pulpcore 3.9.
  `#4689 <https://pulp.plan.io/issues/4689>`_
- Added progress reporting for pulp imports.
  `#6559 <https://pulp.plan.io/issues/6559>`_
- Exposed ``aiohttp.ClientTimeout`` fields in ``Remote`` as ``connect_timeout``,
  ``sock_connect_timeout``, ``sock_read_timeout``, and ``total_timeout``.

  This replaces the previous hard-coded 600 second timeout for sock_connect and sock_read,
  giving per-``Remote`` control of all four ``ClientTimeout`` fields to the user.
  `#7201 <https://pulp.plan.io/issues/7201>`_
- Enabled users to add checksums to ALLOWED_CONTENT_CHECKSUMS by allowing them to populate checksums
  with handle-artifact-checksums command.
  `#7561 <https://pulp.plan.io/issues/7561>`_
- Added version information to api docs.
  `#7569 <https://pulp.plan.io/issues/7569>`_
- Made signing services to be immutable. This requires content signers to create a new signing
  service explicitly when a change occurs.
  `#7701 <https://pulp.plan.io/issues/7701>`_
- Added support for repairing Pulp by detecting and redownloading missing or corrupted artifact files. Sending a POST request to ``/pulp/api/v3/repair/`` will trigger a task that scans all artifacts for missing and corrupted files in Pulp storage, and will attempt to redownload them from the original remote. Specifying ``verify_checksums=False`` when POSTing to the same endpoint will skip checking the hashes of the files (corruption detection) and will instead just look for missing files.

  The ``verify_checksums`` POST parameter was added to the existing "repository version repair" endpoint as well.
  `#7755 <https://pulp.plan.io/issues/7755>`_
- Added check to prevent Pulp to start if there are Artifacts with forbidden checksums.
  `#7914 <https://pulp.plan.io/issues/7914>`_


Bugfixes
~~~~~~~~

- Fixed a serious bug data integrity bug where some Artifact files could be silently deleted from storage in specific circumstances.
  `#7676 <https://pulp.plan.io/issues/7676>`_
- Moved the initial creation of access_policies to post_migrate signal.
  This enforces their existance both with migrate and flush.
  `#7710 <https://pulp.plan.io/issues/7710>`_
- Fixed incremental export to happen if start_version provided, even if last_export is null.
  `#7716 <https://pulp.plan.io/issues/7716>`_
- Fixed a file descriptor leak during repository version repair operations.
  `#7735 <https://pulp.plan.io/issues/7735>`_
- Fixed bug where exporter directory existed and was writable but not owned by worker process and thus
  not chmod-able.
  `#7829 <https://pulp.plan.io/issues/7829>`_
- Properly namespaced the `viewset_name` in `AccessPolicy` to avoid naming conflicts in plugins.
  `#7845 <https://pulp.plan.io/issues/7845>`_
- Update jquery version from 3.3.1 to 3.5.1 in API.html template. It is the version provided by djangorestframework~=3.12.2
  `#7850 <https://pulp.plan.io/issues/7850>`_
- Prevented a Redis failure scenario from causing the tasking system to back up due to "tasking system
  locks" not being released, even on worker restart.
  `#7907 <https://pulp.plan.io/issues/7907>`_
- Use subclassed plugin downloaders during the pulp repair.
  `#7909 <https://pulp.plan.io/issues/7909>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added requirement to record a demo with PRs of substantial change.
  `#7703 <https://pulp.plan.io/issues/7703>`_
- Removed outdated reference stating Pulp did not have an SELinux policy.
  `#7793 <https://pulp.plan.io/issues/7793>`_


Removals
~~~~~~~~

- The local file system directory used for uploaded chunks is specified by the setting
  CHUNKED_UPLOAD_DIR. Users are encouraged to remove all uncommitted uploaded files before
  applying this change.
  `#4498 <https://pulp.plan.io/issues/4498>`_


Misc
~~~~

- `#7690 <https://pulp.plan.io/issues/7690>`_, `#7753 <https://pulp.plan.io/issues/7753>`_, `#7902 <https://pulp.plan.io/issues/7902>`_, `#7890 <https://pulp.plan.io/issues/7890>`_

Plugin API
----------

Features
~~~~~~~~

- Added pre_save hook to Artifact to enforce checksum rules implied by ALLOWED_CONTENT_CHECKSUMS.
  `#7696 <https://pulp.plan.io/issues/7696>`_
- Enabled plugin writers to retrieve a request object from a serializer when look ups are
  performed from within the task serializer.
  `#7718 <https://pulp.plan.io/issues/7718>`_
- Expose ProgressReportSerializer through `pulpcore.plugin`
  `#7759 <https://pulp.plan.io/issues/7759>`_
- Allowed plugin writers to access the models Upload and UploadChunk
  `#7833 <https://pulp.plan.io/issues/7833>`_
- Exposed ``pulpcore.plugin.constants.ALL_KNOWN_CONTENT_CHECKSUMS``.
  `#7897 <https://pulp.plan.io/issues/7897>`_
- Added ``UnsupportedDigestValidationError`` to ``pulpcore.plugins.exceptions``. Going
  forward, plugin authors can expect to find all unique exceptions under
  ``pulpcore.plugin.exceptions``.
  `#7908 <https://pulp.plan.io/issues/7908>`_


Deprecations
~~~~~~~~~~~~

- Plugins are encouraged to define a ``version`` attribute on their subclass of
  ``PulpPluginAppConfig``. If undefined while Pulp loads a warning is now shown to encourage plugin
  writers to implement this attribute, which will be required starting in pulpcore==3.10.
  `#6671 <https://pulp.plan.io/issues/6671>`_
- Using the ViewSet's classname to identify its AccessPolicy has been deprecated and is slated for removal in 3.10.
  Instead the urlpattern is supposed to be used.

  Plugins with existing AccessPolicies should add a data migration to rename their AccessPolicies:

  ::
      access_policy = AccessPolicy.get(viewset_name="MyViewSet")
      access_policy.viewset_name = "objectclass/myplugin/myclass"
      access_policy.save()
  `#7845 <https://pulp.plan.io/issues/7845>`_
- The ``pulpcore.plugin.models.UnsupportedDigestValidationError`` is being deprecated and
  will be removed in 3.10.

  It can now be found at ``pulpcore.plugin.exceptions.UnsupportedDigestValidationError``
  instead; please change any code that imports it to access it from its new location.
  `#7908 <https://pulp.plan.io/issues/7908>`_


3.8.1 (2020-10-30)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a serious bug data integrity bug where some Artifact files could be silently deleted from storage in specific circumstances. (Backported from https://pulp.plan.io/issues/7676)
  `#7758 <https://pulp.plan.io/issues/7758>`_


Plugin API
----------

No significant changes.


3.8.0 (2020-10-20)
==================
REST API
--------

Features
~~~~~~~~

- Added check to prevent users from adding checksums to ``ALLOWED_CONTENT_CHECKSUMS`` if there are
  Artifacts without those checksums.
  `#7487 <https://pulp.plan.io/issues/7487>`_
- Django admin site URL is configurable via `ADMIN_SITE_URL` settings parameter.
  `#7637 <https://pulp.plan.io/issues/7637>`_
- Always set a default for DJANGO_SETTINGS_MODULE. This means the services files don't need to.
  `#7720 <https://pulp.plan.io/issues/7720>`_


Bugfixes
~~~~~~~~

- Fix a warning inappropriately logged when cancelling a task.
  `#4559 <https://pulp.plan.io/issues/4559>`_
- When a task is canceled, we now set the state of all incomplete "progress reports" to canceled as well.
  `#4921 <https://pulp.plan.io/issues/4921>`_
- Properly handle duplicate content during synchronization and migration from Pulp 2 to 3.
  `#7147 <https://pulp.plan.io/issues/7147>`_
- Enable content streaming for RepositoryVersionDistribution
  `#7568 <https://pulp.plan.io/issues/7568>`_
- Change dropped DRF filter to django urlize.
  `#7634 <https://pulp.plan.io/issues/7634>`_
- Added some more files to MANIFEST.in.
  `#7656 <https://pulp.plan.io/issues/7656>`_
- Updated dynaconf requirement to prevent use of older buggy versions.
  `#7682 <https://pulp.plan.io/issues/7682>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updated examples of auto-distribution.
  `#5247 <https://pulp.plan.io/issues/5247>`_
- Improved testing section in Pulp contributor docs.
  Mentioned `prestart`, `pminio`, `pfixtures` and `phelp`.
  `#7475 <https://pulp.plan.io/issues/7475>`_
- Fix an erroneous API endpoint in the "upload and publish" workflow documentation.
  `#7655 <https://pulp.plan.io/issues/7655>`_
- Documented that we don't support backporting migrations.
  `#7657 <https://pulp.plan.io/issues/7657>`_


Plugin API
----------

Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Removed mentions of semver in the plugin API docs, and replaced them with a link to the deprecation policy where appropriate.
  `#7555 <https://pulp.plan.io/issues/7555>`_


3.7.6 (2021-04-29)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Backported a fix for on-demand sync/migration of repositories that don't have sha256 checksums.
  `#8651 <https://pulp.plan.io/issues/8651>`_


Plugin API
----------

No significant changes.


3.7.5 (2021-04-12)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Backported fixes for artifact handling important for pulp-2to3-migration plugin use cases.
  `#8485 <https://pulp.plan.io/issues/8485>`_
- Allowed to use PyYAML 5.4 which contains a patch for `CVE-2020-14343 <https://nvd.nist.gov/vuln/detail/CVE-2020-14343>`_.
  `#8540 <https://pulp.plan.io/issues/8540>`_


Plugin API
----------

No significant changes.


3.7.4 (2021-03-15)
==================
REST API
--------

Bugfixes
~~~~~~~~

- No longer load .env files. They are not used by Pulp but potentially can break the setup.
  `#8373 <https://pulp.plan.io/issues/8373>`_


Plugin API
----------

No significant changes.


3.7.3 (2020-10-28)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a serious bug data integrity bug where some Artifact files could be silently deleted from storage in specific circumstances. (Backported from https://pulp.plan.io/issues/7676)
  `#7757 <https://pulp.plan.io/issues/7757>`_


Plugin API
----------

No significant changes.


3.7.2 (2020-10-21)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Properly handle duplicate content during synchronization and migration from Pulp 2 to 3.
  `#7702 <https://pulp.plan.io/issues/7702>`_
- Fixed incremental export to happen if start_version provided, even if last_export is null.
  `#7725 <https://pulp.plan.io/issues/7725>`_


Plugin API
----------

No significant changes.


3.7.1 (2020-09-29)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Including functest_requirements.txt on MANIFEST.in
  `#7610 <https://pulp.plan.io/issues/7610>`_


Plugin API
----------

No significant changes.


3.7.0 (2020-09-22)
==================
REST API
--------

Features
~~~~~~~~

- Added setting ALLOWED_CONTENT_CHECKSUMS to support limiting the checksum-algorithms Pulp uses.
  `#5216 <https://pulp.plan.io/issues/5216>`_
- Added progress-reports to the PulpExport task.
  `#6541 <https://pulp.plan.io/issues/6541>`_
- Improve performance and memory consumption of orphan cleanup.
  `#6581 <https://pulp.plan.io/issues/6581>`_
- Extra require: s3, azure, prometheus and test
  `#6844 <https://pulp.plan.io/issues/6844>`_
- Added the toc_info attribute with filename/sha256sum to PulpExport, to enable direct access to the export-TOC.
  `#7221 <https://pulp.plan.io/issues/7221>`_
- Taught export-process to clean up broken files if the export fails.
  `#7246 <https://pulp.plan.io/issues/7246>`_
- Added the django-cleanup handlers for removing files stored within FileField
  `#7316 <https://pulp.plan.io/issues/7316>`_
- Added deprecations section to the changelog.
  `#7415 <https://pulp.plan.io/issues/7415>`_


Bugfixes
~~~~~~~~

- Address some problems with stuck tasks when connection to redis is interrupted.
  `#6449 <https://pulp.plan.io/issues/6449>`_
- Fixed a bug where creating an incomplete repository version (via canceled or failed task) could cause future operations to fail.
  `#6463 <https://pulp.plan.io/issues/6463>`_
- Added validation for unknown serializers' fields
  `#7245 <https://pulp.plan.io/issues/7245>`_
- Fixed: `PulpTemporaryFile` stored in the wrong location
  `#7319 <https://pulp.plan.io/issues/7319>`_
- Fixed an edge case where canceled tasks might sometimes be processed and marked completed.
  `#7389 <https://pulp.plan.io/issues/7389>`_
- Fixed pulp-export scenario where specifying full= could fail silently.
  `#7403 <https://pulp.plan.io/issues/7403>`_
- Fixed OpenAPI creation response status code to 201
  `#7444 <https://pulp.plan.io/issues/7444>`_
- The ``AccessPolicy.permissions_assignment`` can now be null, which some viewset endpoints may
  require.
  `#7448 <https://pulp.plan.io/issues/7448>`_
- Taught export to insure export-dir was writeable by group as well as owner.
  `#7459 <https://pulp.plan.io/issues/7459>`_
- Fixed orphan cleanup for subrepositories (e.g. an add-on repository in RPM distribution tree repository).
  `#7460 <https://pulp.plan.io/issues/7460>`_
- Fixed issue with reserved resources not being displayed for waiting tasks.
  `#7497 <https://pulp.plan.io/issues/7497>`_
- Fixed broken bindings resulting from drf-spectacular 0.9.13 release.
  `#7510 <https://pulp.plan.io/issues/7510>`_
- Fix filesystem exports failing due to undefinied ``validate_path`` method.
  `#7521 <https://pulp.plan.io/issues/7521>`_
- Fix a bug that prevented users from adding permissions for models have conflicting names across different django apps.
  `#7541 <https://pulp.plan.io/issues/7541>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added pulp 2 obsolete concepts (consumers, applicability).
  `#6255 <https://pulp.plan.io/issues/6255>`_


Misc
~~~~

- `#7508 <https://pulp.plan.io/issues/7508>`_


Plugin API
----------

Features
~~~~~~~~

- Enabled the automatic removal of files, which are stored in FileField, when a corresponding
  model's delete() method is invoked
  `#7316 <https://pulp.plan.io/issues/7316>`_
- Add add_and_remove task to pulpcore.plugin.tasking
  `#7351 <https://pulp.plan.io/issues/7351>`_
- Added deprecations section to the plugin api changelog.
  `#7415 <https://pulp.plan.io/issues/7415>`_


Bugfixes
~~~~~~~~

- The ``AccessPolicy.permissions_assignment`` can now be null, which some viewset endpoints may
  require.
  `#7448 <https://pulp.plan.io/issues/7448>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added an example how to use a serializer to create validated objects.
  `#5927 <https://pulp.plan.io/issues/5927>`_
- Document the URLField OpenAPI issue
  `#6828 <https://pulp.plan.io/issues/6828>`_
- Added all exported models to the autogenerated API reference.
  `#7045 <https://pulp.plan.io/issues/7045>`_
- Updated docs recommending plugins to rely on a 1-release deprecation process for backwards
  incompatible changes in the ``pulpcore.plugin``.
  `#7413 <https://pulp.plan.io/issues/7413>`_
- Adds plugin writer docs on how to ship snippets which override default webserver routes provided by
  the installer.
  `#7471 <https://pulp.plan.io/issues/7471>`_
- Revises the "installation plugin custom tasks" documentation to reflect that plugin writers can
  contribute their custom installation needs directly to the installer.
  `#7523 <https://pulp.plan.io/issues/7523>`_


Misc
~~~~

- `#7270 <https://pulp.plan.io/issues/7270>`_


3.6.5 (2020-10-28)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a bug where creating an incomplete repository version (via canceled or failed task) could cause future operations to fail. (Backported from https://pulp.plan.io/issues/6463)
  `#7737 <https://pulp.plan.io/issues/7737>`_


Plugin API
----------

No significant changes.


3.6.4 (2020-09-23)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed broken bindings resulting from drf-spectacular 0.9.13 release.
  `#7510 <https://pulp.plan.io/issues/7510>`_


Plugin API
----------

No significant changes.


3.6.3 (2020-09-04)
==================
REST API
--------

Misc
~~~~

- `#7450 <https://pulp.plan.io/issues/7450>`_


Plugin API
----------

No significant changes.


3.6.2 (2020-09-02)
==================
REST API
--------

No significant changes.


Plugin API
----------

Bugfixes
~~~~~~~~

- Remove customized operation_id from OrphansView
  `#7446 <https://pulp.plan.io/issues/7446>`_


3.6.1 (2020-09-01)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixing groups API validation
  `#7329 <https://pulp.plan.io/issues/7329>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updated Pypi installation step.
  `#6305 <https://pulp.plan.io/issues/6305>`_
- Added hardware requirements.
  `#6856 <https://pulp.plan.io/issues/6856>`_


Misc
~~~~

- `#7229 <https://pulp.plan.io/issues/7229>`_


Plugin API
----------

Bugfixes
~~~~~~~~

- Fix custom operation_id's from OpenAPI
  `#7341 <https://pulp.plan.io/issues/7341>`_
- OpenAPI: do not discard components without properties
  `#7347 <https://pulp.plan.io/issues/7347>`_


3.6.0 (2020-08-13)
==================
REST API
--------

Features
~~~~~~~~

- Added table-of-contents to export and gave import a toc= to find/reassemble pieces on import.
  `#6737 <https://pulp.plan.io/issues/6737>`_
- Added ability to associate a Remote with a Repository so users no longer have to specify Remote when
  syncing.
  `#7015 <https://pulp.plan.io/issues/7015>`_
- The `/pulp/api/v3/access_policies/` endpoint is available for reading and modifying the AccessPolicy
  used for Role Based Access Control for all Pulp endpoints. This allows for complete customization
  of the Authorization policies.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  `#7160 <https://pulp.plan.io/issues/7160>`_
- The `/pulp/api/v3/access_policies/` endpoint also includes a `permissions_assignment` section which
  customizes the permissions assigned to new objects. This allows for complete customization for how
  new objects work with custom define Authorization policies.
  `#7210 <https://pulp.plan.io/issues/7210>`_
- The `/pulp/api/v3/users/` endpoint is available for reading the Users, Group membership, and
  Permissions.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  `#7231 <https://pulp.plan.io/issues/7231>`_
- The `/pulp/api/v3/groups/` endpoint is available for reading the Groups, membership, and
  Permissions.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  `#7232 <https://pulp.plan.io/issues/7232>`_
- The `/pulp/api/v3/tasks/` endpoint now provides a user-isolation behavior for non-admin users. This
  policy is controllable at the `/pulp/api/v3/access_policies/` endpoint.

  NOTE: The user-isolation behavior is in "tech preview" and production systems are recommended to
  continue using the build-in ``admin`` user only.
  `#7301 <https://pulp.plan.io/issues/7301>`_
- Extended endpoint `/pulp/api/v3/groups/:pk/users` to add and remove users from a group.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  `#7310 <https://pulp.plan.io/issues/7310>`_
- Extended endpoints `/pulp/api/v3/groups/:pk/model_permissions` and
  `/pulp/api/v3/groups/:pk/object_permissions` to add and remove permissions from a group.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  `#7311 <https://pulp.plan.io/issues/7311>`_


Bugfixes
~~~~~~~~

- WorkerDirectory.delete() no longer recursively trys to delete itself when encountering a permission error
  `#6504 <https://pulp.plan.io/issues/6504>`_
- Stopped preventing removal of PulpExport/Exporter when last-export existed.
  `#6555 <https://pulp.plan.io/issues/6555>`_
- First time on demand content requests appear in the access log.
  `#7002 <https://pulp.plan.io/issues/7002>`_
- Fixed denial of service caused by extra slashes in content urls.
  `#7066 <https://pulp.plan.io/issues/7066>`_
- Set a default DJANGO_SETTINGS_MODULE env var in content app
  `#7179 <https://pulp.plan.io/issues/7179>`_
- Added plugin namespace to openapi href identifier.
  `#7209 <https://pulp.plan.io/issues/7209>`_
- By default, html in field descriptions filtered out in REST API docs unless 'include_html' is set.
  `#7299 <https://pulp.plan.io/issues/7299>`_
- Fixed plugin filtering in bindings to work independently from "bindings" parameter.
  `#7306 <https://pulp.plan.io/issues/7306>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Made password variable consistent with Ansible installer example playbook
  `#7065 <https://pulp.plan.io/issues/7065>`_
- Fixed various docs bugs in the pulpcore docs.
  `#7090 <https://pulp.plan.io/issues/7090>`_
- Adds documentation about SSL configuration requirements for reverse proxies.
  `#7285 <https://pulp.plan.io/issues/7285>`_
- Fixed REST API docs.
  `#7292 <https://pulp.plan.io/issues/7292>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removed unnecessary fields from the import/export transfer.
  `#6515 <https://pulp.plan.io/issues/6515>`_
- Upgrading the api documentation from OpenAPI v2 to OpenAPI v3.
  - Methods signatures for bindings may change.
  `#7108 <https://pulp.plan.io/issues/7108>`_
- Changed default ``download_concurrency`` on Remotes from 20 to 10 to avoid connection problems. Also
  updated existing Remotes with ``download_concurrency`` of 20 to 10.
  `#7212 <https://pulp.plan.io/issues/7212>`_


Misc
~~~~

- `#6807 <https://pulp.plan.io/issues/6807>`_, `#7142 <https://pulp.plan.io/issues/7142>`_, `#7196 <https://pulp.plan.io/issues/7196>`_


Plugin API
----------

Features
~~~~~~~~

- Adding `PulpTemporaryFile` for handling temporary files between the viewset and triggered tasks
  `#6749 <https://pulp.plan.io/issues/6749>`_
- ``RepositorySyncURLSerializer`` will now check remote on the repository before it raises an
  exception if the remote param is not set.
  `#7015 <https://pulp.plan.io/issues/7015>`_
- Added a hook on ``Repository`` called ``artifacts_for_version()`` that plugins can override to
  modify the logic behind ``RepositoryVersion.artifacts``. For now, this is used when exporting
  artifacts.
  `#7021 <https://pulp.plan.io/issues/7021>`_
- Enabling plugin writers to have more control on `HttpDownloader` response codes 400+
  by subclassing `HttpDownloader` and overwriting `raise_for_status` method
  `#7117 <https://pulp.plan.io/issues/7117>`_
- `BaseModel` now inherits from `LifecycleModel` provided by `django-lifecycle` allowing any subclass
  to also use it instead of signals.
  `#7151 <https://pulp.plan.io/issues/7151>`_
- A new `pulpcore.plugin.models.AutoDeleteObjPermsMixin` object can be added to models to
  automatically delete all user and group permissions for an object just before the object is deleted.
  This provides an easy cleanup mechanism and can be added to models as a mixin. Note that your model
  must support `django-lifecycle` to use this mixin.
  `#7157 <https://pulp.plan.io/issues/7157>`_
- A new model `pulpcore.plugin.models.AccessPolicy` is available to store AccessPolicy statements in
  the database. The model's `statements` field stores the list of policy statements as a JSON field.
  The `name` field stores the name of the Viewset the `AccessPolicy` is protecting.

  Additionally, the `pulpcore.plugin.access_policy.AccessPolicyFromDB` is a drf-access-policy which
  viewsets can use to protect their viewsets with. See the :ref:`viewset_enforcement` for more
  information on this.
  `#7158 <https://pulp.plan.io/issues/7158>`_
- Adds the `TaskViewSet` and `TaskGroupViewSet` objects to the plugin api.
  `#7187 <https://pulp.plan.io/issues/7187>`_
- Enabled plugin writers to create immutable repository ViewSets
  `#7191 <https://pulp.plan.io/issues/7191>`_
- A new `pulpcore.plugin.models.AutoAddObjPermsMixin` object can be added to models to automatically
  add permissions for an object just after the object is created. This is controlled by data saved in
  the `permissions_assignment` attribute of the `pulpcore.plugin.models.AccessPolicy` allowing users
  to control what permissions are created. Note that your model must support `django-lifecycle` to use
  this mixin.
  `#7210 <https://pulp.plan.io/issues/7210>`_
- Added ability for plugin writers to set a ``content_mapping`` property on content resources to
  provide a custom mapping of content to repositories.
  `#7252 <https://pulp.plan.io/issues/7252>`_
- Automatically excluding ``pulp_id``, ``pulp_created``, and ``pulp_last_updated`` for
  ``QueryModelResources``.
  `#7277 <https://pulp.plan.io/issues/7277>`_
- Viewsets that subclass ``pulpcore.plugin.viewsets.NamedModelViewSet` can declare the
  ``queryset_filtering_required_permission`` class attribute naming the permission required to view
  an object. See the :ref:`queryset_scoping` documentation for more information.
  `#7300 <https://pulp.plan.io/issues/7300>`_


Bugfixes
~~~~~~~~

- Making operation_id unique
  `#7233 <https://pulp.plan.io/issues/7233>`_
- Making ReDoc OpenAPI summary human readable
  `#7237 <https://pulp.plan.io/issues/7237>`_
- OpenAPI schema generation from CLI
  `#7258 <https://pulp.plan.io/issues/7258>`_
- Allow `pulpcore.plugin.models.AutoAddObjPermsMixin.add_for_object_creator` to skip assignment of
  permissions if there is no known user. This allows endpoints that do not use authorization but still
  create objects in the DB to execute without error.
  `#7312 <https://pulp.plan.io/issues/7312>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Omit a view/viewset from the OpenAPI schema
  `#7133 <https://pulp.plan.io/issues/7133>`_
- Added plugin writer docs for ``BaseContentResource``.
  `#7296 <https://pulp.plan.io/issues/7296>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Newlines in certificate string (ca_cert, client_cert, client_key) on Remotes are not required to be escaped.
  `#6735 <https://pulp.plan.io/issues/6735>`_
- Replaced drf-yasg with drf-spectacular.
  - This updates the api documentation to openapi v3.
  - Plugins may require changes.
  - Methods signatures for bindings may change.
  `#7108 <https://pulp.plan.io/issues/7108>`_
- Moving containers from pulpcore to pulp-operator
  `#7171 <https://pulp.plan.io/issues/7171>`_


3.5.0 (2020-07-08)
==================
REST API
--------

Features
~~~~~~~~

- Added start_versions= to export to allow for arbitrary incremental exports.
  `#6763 <https://pulp.plan.io/issues/6763>`_
- Added GroupProgressReport to track progress in a TaskGroup.
  `#6858 <https://pulp.plan.io/issues/6858>`_
- Provide a user agent string with all aiohttp requests by default.
  `#6954 <https://pulp.plan.io/issues/6954>`_


Bugfixes
~~~~~~~~

- Fixed 'integer out of range' error during sync by changing RemoteArtifact size field to BigIntegerField.
  `#6717 <https://pulp.plan.io/issues/6717>`_
- Added a more descriptive error message that is shown when CONTENT_ORIGIN is not properly configured
  `#6771 <https://pulp.plan.io/issues/6771>`_
- Including requirements.txt on MANIFEST.in
  `#6888 <https://pulp.plan.io/issues/6888>`_
- Corrected a number of filters to be django-filter-2.3.0-compliant.
  `#6915 <https://pulp.plan.io/issues/6915>`_
- Locked Content table to prevent import-deadlock.
  `#7073 <https://pulp.plan.io/issues/7073>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updating installation docs
  `#6836 <https://pulp.plan.io/issues/6836>`_
- Fixed a number of typos in the import/export workflow docs.
  `#6919 <https://pulp.plan.io/issues/6919>`_
- Fixed docs which claim that admin user has a default password.
  `#6992 <https://pulp.plan.io/issues/6992>`_
- Fixed broken link to content plugins web page
  `#7017 <https://pulp.plan.io/issues/7017>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removes the Write models from the OpenAPI schema.
  Brings back the models that were accidentally removed from the OpenAPI schema in 3.4.0 release.
  `#7087 <https://pulp.plan.io/issues/7087>`_


Misc
~~~~

- `#6483 <https://pulp.plan.io/issues/6483>`_, `#6925 <https://pulp.plan.io/issues/6925>`_


Plugin API
----------

Features
~~~~~~~~

- Views can specify the tag name with `pulp_tag_name`
  `#6832 <https://pulp.plan.io/issues/6832>`_
- Added GroupProgressReport to track progress in a TaskGroup.
  `#6858 <https://pulp.plan.io/issues/6858>`_
- Exported the symbols `serializers.SingleContentArtifactField` and `files.PulpTemporaryUploadedFile`.
  `#7088 <https://pulp.plan.io/issues/7088>`_


----


3.4.0 (2020-05-27)
==================
REST API
--------

Features
~~~~~~~~

- Implemented incremental-exporting for PulpExport.
  `#6136 <https://pulp.plan.io/issues/6136>`_
- Added support for S3 and other non-filesystem storage options to pulp import/export functionality.
  `#6456 <https://pulp.plan.io/issues/6456>`_
- Optimized imports by having repository versions processed using child tasks.
  `#6484 <https://pulp.plan.io/issues/6484>`_
- Added repository type check during Pulp imports.
  `#6532 <https://pulp.plan.io/issues/6532>`_
- Added version checking to import process.
  `#6558 <https://pulp.plan.io/issues/6558>`_
- Taught PulpExport to export by RepositoryVersions if specified.
  `#6566 <https://pulp.plan.io/issues/6566>`_
- Task groups now have an 'all_tasks_dispatched' field which denotes that no more tasks will spawn
  as part of this group.
  `#6591 <https://pulp.plan.io/issues/6591>`_
- Taught export how to split export-file into chunk_size bytes.
  `#6736 <https://pulp.plan.io/issues/6736>`_


Bugfixes
~~~~~~~~

- Remote fields `username` and `password` show up in:
  REST docs, API responses, and are available in the bindings.
  `#6346 <https://pulp.plan.io/issues/6346>`_
- Fixed a bug, where the attempt to cancel a completed task lead to a strange response.
  `#6465 <https://pulp.plan.io/issues/6465>`_
- Fixed KeyError during OpenAPI schema generation.
  `#6468 <https://pulp.plan.io/issues/6468>`_
- Added a missing trailing slash to distribution's base_url
  `#6507 <https://pulp.plan.io/issues/6507>`_
- Fixed a bug where the wrong kind of error was being raised for href parameters of mismatched types.
  `#6521 <https://pulp.plan.io/issues/6521>`_
- containers: Fix pulp_rpm 3.3.0 install by replacing the python3-createrepo_c RPM with its build-dependencies, so createrep_c gets installed & built from PyPI
  `#6523 <https://pulp.plan.io/issues/6523>`_
- Fixed OpenAPI schema for importer and export APIs.
  `#6556 <https://pulp.plan.io/issues/6556>`_
- Normalized export-file-path for PulpExports.
  `#6564 <https://pulp.plan.io/issues/6564>`_
- Changed repository viewset to use the general_update and general_delete tasks.
  This fixes a bug where updating specialized fields of a repository was impossible due to using the wrong serializer.
  `#6569 <https://pulp.plan.io/issues/6569>`_
- Only uses multipart OpenAPI Schema when dealing with `file` fields
  `#6702 <https://pulp.plan.io/issues/6702>`_
- Fixed a bug that prevented write_only fields from being present in the API docs and bindings
  `#6775 <https://pulp.plan.io/issues/6775>`_
- Added proper headers for index.html pages served by content app.
  `#6802 <https://pulp.plan.io/issues/6802>`_
- Removed Content-Encoding header from pulpcore-content responses.
  `#6831 <https://pulp.plan.io/issues/6831>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Adding docs for importing and exporting from Pulp to Pulp.
  `#6364 <https://pulp.plan.io/issues/6364>`_
- Add some documentation around TaskGroups.
  `#6641 <https://pulp.plan.io/issues/6641>`_
- Introduced a brief explanation about `pulp_installer`
  `#6674 <https://pulp.plan.io/issues/6674>`_
- Added a warning that the REST API is not safe for multi-user use until RBAC is implemented.
  `#6692 <https://pulp.plan.io/issues/6692>`_
- Updated the required roles names
  `#6758 <https://pulp.plan.io/issues/6758>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed repositories field on ``/pulp/api/v3/exporters/core/pulp/`` from UUIDs to hrefs.
  `#6457 <https://pulp.plan.io/issues/6457>`_
- Imports now spawn child tasks which can be fetched via the ``child_tasks`` field of the import task.
  `#6484 <https://pulp.plan.io/issues/6484>`_
- Content of ssl certificates and keys changed to be return their full value instead of sha256 through REST API.
  `#6691 <https://pulp.plan.io/issues/6691>`_
- Replaced PulpExport filename/sha256 fields, with output_info_file, a '<filename>': '<hash>' dictionary.
  `#6736 <https://pulp.plan.io/issues/6736>`_


Misc
~~~~

- `#5020 <https://pulp.plan.io/issues/5020>`_, `#6421 <https://pulp.plan.io/issues/6421>`_, `#6477 <https://pulp.plan.io/issues/6477>`_, `#6539 <https://pulp.plan.io/issues/6539>`_, `#6542 <https://pulp.plan.io/issues/6542>`_, `#6544 <https://pulp.plan.io/issues/6544>`_, `#6572 <https://pulp.plan.io/issues/6572>`_, `#6583 <https://pulp.plan.io/issues/6583>`_, `#6695 <https://pulp.plan.io/issues/6695>`_, `#6803 <https://pulp.plan.io/issues/6803>`_, `#6804 <https://pulp.plan.io/issues/6804>`_


Plugin API
----------

Features
~~~~~~~~

- Added new NoArtifactContentUploadSerializer and NoArtifactContentUploadViewSet to enable plugin
  writers to upload content without storing an Artifact
  `#6281 <https://pulp.plan.io/issues/6281>`_
- Added view_name_pattern to DetailRelatedField and DetailIdentityField to properly identify wrong resource types.
  `#6521 <https://pulp.plan.io/issues/6521>`_
- Added support for Distributions to provide non-Artifact content via a content_handler.
  `#6570 <https://pulp.plan.io/issues/6570>`_
- Added constants to the plugin API at ``pulpcore.plugin.constants``.
  `#6579 <https://pulp.plan.io/issues/6579>`_
- TaskGroups now have an 'all_tasks_dispatched' field that can be used to notify systems that no
  further tasks will be dispatched for a TaskGroup. Plugin writers should call ".finish()" on all
  TaskGroups created once they are done using them to set this field.
  `#6591 <https://pulp.plan.io/issues/6591>`_


Bugfixes
~~~~~~~~

- Added ``RemoteFilter`` to the plugin API as it was missing but used by plugin_template.
  `#6563 <https://pulp.plan.io/issues/6563>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Fields: `username` and `password` will be returned to the rest API user requesting a `Remote`
  `#6346 <https://pulp.plan.io/issues/6346>`_
- Rehomed QueryModelResource to pulpcore.plugin.importexport.
  `#6514 <https://pulp.plan.io/issues/6514>`_
- The :meth:`pulpcore.content.handler.Handler.list_directory` function now returns a set of strings where it returned a string of HTML before.
  `#6570 <https://pulp.plan.io/issues/6570>`_


----


3.3.1 (2020-05-07)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed partial and general update calls for SecretCharField on the Remote.
  `#6565 <https://pulp.plan.io/issues/6565>`_
- Fixed bug where ``TaskGroup`` was showing up as null for ``created_resources`` in tasks.
  `#6573 <https://pulp.plan.io/issues/6573>`_


Plugin API
----------

Features
~~~~~~~~

- Add TaskGroup to the plugin API.
  `#6603 <https://pulp.plan.io/issues/6603>`_


----


3.3.0 (2020-04-15)
==================
REST API
--------

Features
~~~~~~~~

- Added support for repairing a RepositoryVersion by redownloading corrupted artifact files.
  Sending a POST request to
  ``/pulp/api/v3/repositories/<plugin>/<type>/<repository-uuid>/versions/<version-number>/repair/``
  will trigger a task that scans all associated artfacts and attempts to fetch missing or corrupted ones again.
  `#5613 <https://pulp.plan.io/issues/5613>`_
- Added support for exporting pulp-repo-versions. POSTing to an exporter using the
  ``/pulp/api/v3/exporters/core/pulp/<exporter-uuid>/exports/`` API will instantiate a
  PulpExport entity, which will generate an export-tar.gz file at
  ``<exporter.path>/export-<export-uuid>-YYYYMMDD_hhMM.tar.gz``
  `#6135 <https://pulp.plan.io/issues/6135>`_
- Added API for importing Pulp Exports at ``POST /importers/core/pulp/<uuid>/imports/``.
  `#6137 <https://pulp.plan.io/issues/6137>`_
- Added the new setting CHUNKED_UPLOAD_DIR for configuring a default directory used for uploads
  `#6253 <https://pulp.plan.io/issues/6253>`_
- Exported SigningService in plugin api
  `#6256 <https://pulp.plan.io/issues/6256>`_
- Added name filter for SigningService
  `#6257 <https://pulp.plan.io/issues/6257>`_
- Relationships between tasks that spawn other tasks will be shown in the Task API.
  `#6282 <https://pulp.plan.io/issues/6282>`_
- Added a new APIs for PulpExporters and Exports at ``/exporters/core/pulp/`` and
  ``/exporters/core/pulp/<uuid>/exports/``.
  `#6328 <https://pulp.plan.io/issues/6328>`_
- Added PulpImporter API at ``/pulp/api/v3/importers/core/pulp/``. PulpImporters are used for
  importing exports from Pulp.
  `#6329 <https://pulp.plan.io/issues/6329>`_
- Added an ``ALLOWED_EXPORT_PATHS`` setting with list of filesystem locations that exporters can export to.
  `#6335 <https://pulp.plan.io/issues/6335>`_
- Indroduced `ordering` keyword, which orders the results by specified field.
  Pulp objects will by default be ordered by pulp_created if that field exists.
  `#6347 <https://pulp.plan.io/issues/6347>`_
- Task Groups added -- Plugin writers can spawn tasks as part of a "task group",
  which facilitates easier monitoring of related tasks.
  `#6414 <https://pulp.plan.io/issues/6414>`_


Bugfixes
~~~~~~~~

- Improved the overall performance while syncing very large repositories
  `#6121 <https://pulp.plan.io/issues/6121>`_
- Made chunked uploads to be stored in a local file system instead of a default file storage
  `#6253 <https://pulp.plan.io/issues/6253>`_
- Fixed 500 error when calling modify on nonexistent repo.
  `#6284 <https://pulp.plan.io/issues/6284>`_
- Fixed bug where user could delete repository version 0 but not recreate it by preventing users from
  deleting repo version 0.
  `#6308 <https://pulp.plan.io/issues/6308>`_
- Fixed non unique content units on content list
  `#6347 <https://pulp.plan.io/issues/6347>`_
- Properly sort endpoints during generation of the OpenAPI schema.
  `#6372 <https://pulp.plan.io/issues/6372>`_
- Improved resync performance by up to 2x with a change to the content stages.
  `#6373 <https://pulp.plan.io/issues/6373>`_
- Fixed bug where 'secret' fields would be set to the sha256 checksum of the original value.
  `#6402 <https://pulp.plan.io/issues/6402>`_
- Fixed pulp containers not allowing commands to be run via absolute path.
  `#6420 <https://pulp.plan.io/issues/6420>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Documented bindings installation for a dev environment
  `#6221 <https://pulp.plan.io/issues/6221>`_
- Added documentation for how to write changelog messages.
  `#6336 <https://pulp.plan.io/issues/6336>`_
- Cleared up a line in the database settings documentation that was ambiguous.
  `#6384 <https://pulp.plan.io/issues/6384>`_
- Updated docs to reflect that S3/Azure are supported and no longer tech preview.
  `#6443 <https://pulp.plan.io/issues/6443>`_
- Added tech preview note to docs for importers/exporters.
  `#6454 <https://pulp.plan.io/issues/6454>`_
- Renamed ansible-pulp to pulp_installer (to avoid confusion with pulp-ansible)
  `#6461 <https://pulp.plan.io/issues/6461>`_
- Fixed missing terms in documentation.
  `#6485 <https://pulp.plan.io/issues/6485>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Changing STATIC_URL from `/static/` to `/assets/` for avoiding conflicts
  `#6128 <https://pulp.plan.io/issues/6128>`_
- Exporting now requires the configuration of the ``ALLOWED_EXPORT_PATHS`` setting.  Without this
  configuration, Pulp will not export content to the filesystem.
  `#6335 <https://pulp.plan.io/issues/6335>`_


Misc
~~~~

- `#5826 <https://pulp.plan.io/issues/5826>`_, `#6155 <https://pulp.plan.io/issues/6155>`_, `#6357 <https://pulp.plan.io/issues/6357>`_, `#6450 <https://pulp.plan.io/issues/6450>`_, `#6451 <https://pulp.plan.io/issues/6451>`_, `#6481 <https://pulp.plan.io/issues/6481>`_, `#6482 <https://pulp.plan.io/issues/6482>`_


Plugin API
----------

Features
~~~~~~~~

- Tasks can now be spawned from inside other tasks, and these relationships can be explored
  via the "parent_task" field and "child_tasks" related name on the Task model.
  `#6282 <https://pulp.plan.io/issues/6282>`_
- Added a new Export model, serializer, and viewset.
  `#6328 <https://pulp.plan.io/issues/6328>`_
- Added models Import and Importer (as well as serializers and viewsets) that can be used for
  importing data into Pulp.
  `#6329 <https://pulp.plan.io/issues/6329>`_
- `NamedModelViewSet` uses a default ordering of `-pulp_created` using the `StableOrderingFilter`.
  Users using the `ordering` keyword will be the primary ordering used when specified.
  `#6347 <https://pulp.plan.io/issues/6347>`_
- Added two new repo validation methods (validate_repo_version and validate_duplicate_content).
  `#6362 <https://pulp.plan.io/issues/6362>`_
- enqueue_with_reservation() provides a new optional argument for "task_group".
  `#6414 <https://pulp.plan.io/issues/6414>`_


Bugfixes
~~~~~~~~

- Fixed bug where RepositoryVersion.artifacts returns None.
  `#6439 <https://pulp.plan.io/issues/6439>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Add plugin writer docs on adding MANIFEST.in entry to include ``webserver_snippets`` in the Python
  package.
  `#6249 <https://pulp.plan.io/issues/6249>`_
- Updated the metadata signing plugin writers documentation.
  `#6342 <https://pulp.plan.io/issues/6342>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed master model from FileSystemExporter to Exporter. Plugins will still need to extend
  FileSystemExporter but the master table is now core_exporter. This will require that plugins drop
  and recreate their filesystem exporter tables.
  `#6328 <https://pulp.plan.io/issues/6328>`_
- RepositoryVersion add_content no longer checks for duplicate content.
  `#6362 <https://pulp.plan.io/issues/6362>`_


Misc
~~~~

- `#6342 <https://pulp.plan.io/issues/6342>`_


----


3.2.1 (2020-03-17)
==================
REST API
--------

Misc
~~~~

- `#6244 <https://pulp.plan.io/issues/6244>`_


Plugin API
----------

No significant changes.


----


3.2.0 (2020-02-26)
==================
REST API
--------

Features
~~~~~~~~

- Added a ``pulpcore-manager`` script that is ``django-admin`` only configured with
  ``DJANGO_SETTINGS_MODULE="pulpcore.app.settings"``. This can be used for things like applying
  database migrations or collecting static media.
  `#5859 <https://pulp.plan.io/issues/5859>`_
- Resolve DNS faster with aiodns
  `#6190 <https://pulp.plan.io/issues/6190>`_


Bugfixes
~~~~~~~~

- Considering base version when removing duplicates
  `#5964 <https://pulp.plan.io/issues/5964>`_
- Renames /var/lib/pulp/static/ to /var/lib/pulp/assets/.
  `#5995 <https://pulp.plan.io/issues/5995>`_
- Disabled the trimming of leading and trailing whitespace characters which led to a situation where
  a hash of a certificate computed in Pulp was not equal to a hash generated locally
  `#6025 <https://pulp.plan.io/issues/6025>`_
- Repository.latest_version() considering deleted versions
  `#6147 <https://pulp.plan.io/issues/6147>`_
- Stopped HttpDownloader sending basic auth credentials to redirect location if domains don't match.
  `#6227 <https://pulp.plan.io/issues/6227>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updated docs to suggest to use ``pulpcore-manager`` command instead of ``django-admin`` directly.
  `#5859 <https://pulp.plan.io/issues/5859>`_


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Renaming Repository.last_version to Repository.next_version
  `#6147 <https://pulp.plan.io/issues/6147>`_


Misc
~~~~

- `#6038 <https://pulp.plan.io/issues/6038>`_, `#6202 <https://pulp.plan.io/issues/6202>`_


Plugin API
----------

Features
~~~~~~~~

- Adding not equal lookup to model field filters.
  `#5868 <https://pulp.plan.io/issues/5868>`_


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Adds plugin writer docs on adding custom url routes and having the installer configure the reverse
  proxy to route them.
  `#6209 <https://pulp.plan.io/issues/6209>`_


----


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
