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

3.4.1 (2020-06-03)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Including requirements.txt on MANIFEST.in
  `#6888 <https://pulp.plan.io/issues/6888>`_


Plugin API
----------

No significant changes.


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


----
