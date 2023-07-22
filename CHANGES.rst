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

3.22.9 (2023-07-22)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Resolved a memory leak that could occur while making large repeated queries against the API service.
  :github:`2250`
- Added repeating logic to signalling a task worker subprocess. This should fix a bug where the
  task refuses to be terminated easily.
  :github:`3407`
- Taught repair task to be tolerant in the face of any artifact download failure.
  :github:`4111`


Plugin API
----------

No significant changes.


3.22.8 (2023-07-19)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Made the incremental file export include all published metadata.
  :github:`3941`
- Updates file system exporter to correctly account the start_repository_version  for pass_through publications
  :github:`4051`


Plugin API
----------

No significant changes.


3.22.7 (2023-06-14)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Exports now use gzip compression level 1 rather than compression level 9. Exported archives will
  now be slightly larger, but exports should be much faster. This is considered to be a more
  optimal balance of space/time for the export operation.
  :github:`3869`


Plugin API
----------

No significant changes.


3.22.6 (2023-06-07)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Taught PulpImport to be more robust in the face of previous failed attempts.
  :github:`3737`


Plugin API
----------

No significant changes.


3.22.5 (2023-05-30)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Taught repair task to remove unrepairable corrupted files.
  :github:`1947`
- Taught repair task to continue when encountering a 404 during the repair process.
  :github:`3611`


Plugin API
----------

No significant changes.


3.22.4 (2023-04-11)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed package timestamp on content app to reflect time package was added to the repository.
  :github:`3653`
- Downloader will now attempt to keep the filename of the requested URL intact if one exists.
  :github:`3715`


Plugin API
----------

No significant changes.


3.22.3 (2023-03-06)
===================
REST API
--------

No significant changes.


Plugin API
----------

No significant changes.


3.22.2 (2023-02-02)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Added a ``start_repository_version`` parameter to the file system exporter.

  If specified, it will export only content units that differed between two repository versions.
  :github:`3413`


Plugin API
----------

No significant changes.


3.22.1 (2023-01-20)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed the label migration code for not null constraint errors when objects with and without labels
  are migrated.
  :github:`3495`


Plugin API
----------

No significant changes.


3.22.0 (2022-12-18)
===================
REST API
--------

Features
~~~~~~~~

- Added dates to the HTML pages listing the content of distributions. The timestamp is of when the
  content was created in Pulp.
  :github:`2054`
- Create HiddenFieldsMixin serializer and add hidden_fields to RemoteSerializer and UserSerializer.
  :github:`2825`
- Added ``pulpcore-manager`` command called ``remove-signing-service`` for removing specified signing services.
  :github:`2967`
- Added the option `HIDE_GUARDED_DISTRIBUTIONS` to allow hiding the content guard protected
  distributions from the listing page.
  :github:`3061`
- Added "content_settings" stanza to the /status/ output.
  :github:`3138`
- Added expiry to preauthenticated URLs from `ContentRedirectingContentGuard`.
  :github:`3238`
- Added ``reserved_resources``, ``reserved_resources__in``, ``exclusive_resources``,
  ``exclusive_resources__in``, ``shared_resources`` and ``shared_resources__in`` filter to task
  list endpoint.
  :github:`3280`
- The postgresql version is now included in analytics data posted. The payload looks like:
  ``{`'postgresqlVersion': 90200}``. The integer value is the raw format postgresql reports its
  version as.
  :github:`3396`
- The new ``ANALYTICS`` setting replaced the ``TELEMETRY`` setting to avoid confusion with
  application metrics that will be exposed using OpenTelemetry.
  :github:`3417`


Bugfixes
~~~~~~~~

- Fixed the fs exporter to handle the case where there are pre-existing files in the location that FileSystem attempts to export to you get a FileExistsError.
  :github:`1949`
- The logging_cid field of a task can no longer be an empty string.
  :github:`3016`
- Fixed content-disposition header which is used in the object storage backends.
  :github:`3124`
- Fixed the fs exporter to handle the case where hardlink method was requested but pulp and export locations are in different partitions so can't share the same inode.
  :github:`3187`
- Another guardrail added around content-stages to address deadlock in a specific usecase.
  :github:`3192`
- Fixed bug where installations with at least one pre-release plugin installed were posting to the
  production analytics site instead of the developer analytics site.
  :github:`3213`
- Fixed the worker__in filter for Tasks API.
  :github:`3235`
- Do not expose artifact digest via content-disposition header when using Azure backend.
  :github:`3244`
- Fixed a bug that disallowed non-admin users to purge completed tasks.
  :github:`3263`
- Made ordering consistent between all list API endpoints.
  :github:`3266`
- Another step on closing the deadlock-window when syncing overlapping content.
  :github:`3284`
- Fixed an occasional 500 error when viewing a repository version content summary while performing a content deletion task.
  :github:`3299`
- Fixed an error when raising ``UnexportableArtifactException``.
  :github:`3313`
- Hardened the state transition for tasks and ensured a canceled task will have `finished_at` set.
  :github:`3319`
- Made sure PulpImport's use of tar.extractall() is safe.
  :github:`3323`
- Fixed content disposition header value when content is stored in Azure.
  :github:`3342`
- Fixes schema generation to use proper type `uri` for ``HyperlinkRelatedFilter``.
  :github:`3351`
- Insured that pulp-export correctly locks repos-being-exported.
  :github:`3370`
- Fixed the update of default access policies when fields are missing.
  :github:`3391`
- Fixed the openapi spec of "fields" and "exclude_fields" querystring parameters.
  :github:`3398`
- Fixed label querying performance issues.
  In case some labels could not be migrated properly, a ``datarepair-labels`` command was added.
  :github:`3400`
- Fix migrating Remotes with @ in path
  :github:`3409`
- Fixed the broken link on the root page served by pulpcore-content.
  :github:`3436`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Improvements clarifying how to specify settings and which settings are required.
  :github:`2417`
- Documented Pulpcore and Plugin release processes.
  :github:`3204`
- Separated the user plugin listing from the plugin developer docs more clearly.
  :github:`3260`
- Remove the ansible collection from the recommendation
  :github:`3430`


Deprecations
~~~~~~~~~~~~

- ``TELEMETRY` setting was deprecated in favor of ``ANALYTICS``.
  :github:`3417`


Misc
~~~~

- :github:`3232`, :github:`3333`, :github:`3334`, :github:`3461`


Plugin API
----------

Features
~~~~~~~~

- Added ``get_artifact_url`` to emit preauthed urls to existing artifacts.
  :github:`2785`
- The upload feature was changed to accept already existing content. This allows multiple users
  to own identical content when working with plugins that implement the 'retrieve' method
  inside their ``ContentUpload`` serializers.
  :github:`3081`
- Exposed ``ArtifactResponse`` at ``pulpcore.plugin.responses``.
  :github:`3340`
- Exposed the ``get_url`` util function.
  :github:`3468`


Bugfixes
~~~~~~~~

- Added ``BaseFilterSet`` to ``NamedModelViewSet`` to allow ordering on all list endpoints even
  without specifying a custom filterset class.
  :github:`3266`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added documentation for plugin writers on declaring dependencies.
  :github:`2997`


Removals
~~~~~~~~

- Deprecated model ``Label`` and serializer field ``LabelField`` and ``LabelSelectFilter`` for
  removal in 3.25.
  :github:`3400`


3.21.3 (2022-11-15)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Adjust the dependency on ``cryptography`` to suite more versions of ``pulp-certguard``.
  :github:`3269`
- Insured that pulp-export correctly locks repos-being-exported.
  :github:`3370`
- Fixed the update of default access policies when fields are missing.
  :github:`3391`


Plugin API
----------

No significant changes.


3.21.2 (2022-10-24)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Another step on closing the deadlock-window when syncing overlapping content.
  :github:`3284`
- Fixed content disposition header value when content is stored in Azure.
  :github:`3342`


Plugin API
----------

No significant changes.


3.21.1 (2022-10-18)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed the fs exporter to handle the case where there are pre-existing files in the location that FileSystem attempts to export to you get a FileExistsError.
  :github:`1949`
- Fixed content-disposition header which is used in the object storage backends.
  :github:`3124`
- Fixed the fs exporter to handle the case where hardlink method was requested but pulp and export locations are in different partitions so can't share the same inode.
  :github:`3187`
- Another guardrail added around content-stages to address deadlock in a specific usecase.
  :github:`3192`
- Fixed bug where installations with at least one pre-release plugin installed were posting to the
  production telemetry site instead of the developer telemetry site.
  :github:`3213`
- Do not expose artifact digest via content-disposition header when using Azure backend.
  :github:`3244`


Plugin API
----------

No significant changes.


3.21.0 (2022-09-08)
===================
REST API
--------

Features
~~~~~~~~

- Added an option for automatically creating repositories on the fly during an import procedure. The
  option is disabled by default. Enable it by setting the field ``create_repositories`` to ``True``
  via the REST API.
  :github:`1920`
- Content app now groups distributions in a directory structure on the landing page.
  :github:`1951`
- Added RBAC protection to upload objects.
  :github:`2362`
- New endpoint to list all Remote objects is now available at /pulp/api/v3/remotes/.
  :github:`2530`
- ``HyperlinkRelatedFilter`` can now be filtered by object types and NULL values.

  Repositories can now be filtered by Remotes.
  :github:`2864`
- Introduced the ``with_content`` query parameter that filters distributions by the specified content
  unit.
  :github:`2952`
- Add a debug log to see where is file downloaded from.
  :github:`3088`
- Introduces anonymous telemetry data posting to `<https://analytics.pulpproject.org/>`_. This is
  enabled by default, and can be disabled by setting the ``TELEMETRY`` setting to ``False``. See the
  :ref:`telemetry docs <analytics>` for more info on exactly what is posted along with an example.
  :github:`3115`


Bugfixes
~~~~~~~~

- Fixed the value of the Content-Type header returned for .xml.gz files.
  :github:`2811`
- Improve content app performance on head requests
  :github:`2924`
- Use published relative paths for FS Exporter.
  :github:`2933`
- Configured aiohttp to avoid rewriting redirect URLs, as some web servers (e.g. Amazon CloudFront) can be tempermental about the encoding of the URL.
  :github:`2964`
- Fixed inaccurate 404 error message for content app.
  :github:`2977`
- Fixed variable referenced before assignment error in ``django-admin dump-permissions``.
  :github:`3011`
- Do not create telemetry TaskSchedule for production systems.
  :github:`3015`
- Serialized orphan cleanup tasks with respect to each other to prevent them from failing.
  :github:`3030`
- Fixed 500 error when 'range' header starts with a negative value for 'on-demand' content.
  :github:`3052`
- Fixed bug where 'range' header with a start value greater than size of on-demand content would produce an incomplete response.
  :github:`3054`
- Fixed a bug where Content-Length header value was wrong when on-demand content was requested with
  a Range header that has an end value greater than the size of the content.
  :github:`3055`
- Fixed a bug in the routing logic, where generic base class viewsets were served on actual urls.
  :github:`3056`
- Fixed a bug in import code where all objects imported would also be added to the target repository
  by their UUID. In case of a UUID-collision with content, unwanted content may have ended up being
  in the next repository version.
  :github:`3064`
- Fixed a bug that caused the import machinery to import the same content multiple times in a row.
  :github:`3075`
- Limited access policy reset to viewsets with a default one. This will solve 500 errors when
  trying to reset an access policy whose viewset name is repeated by an abstract base class.
  Stopped reporting on unmodified access policies when migrating.
  :github:`3080`
- Fixed another rare deadlock for high-concurrency/overlapping-content syncs.
  :github:`3111`
- Fixed the progress report counter for imported content units.
  :github:`3113`
- Moved telemetry setup to the pulpcore-worker startup sequence. This will prevent orm calls before
  all apps are ready.
  :github:`3122`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- docs: Update the architecture diagram to reflect the fact that both API and workers talk to redis.
  :github:`3000`
- Multiple updates to the PyPI (manual) install instructions.
  :github:`3051`


Misc
~~~~

- :github:`2445`, :github:`2890`, :github:`3063`, :github:`3091`


Plugin API
----------

Features
~~~~~~~~

- Exposed the ``RepositoryResource`` class to enable plugin writers to customize the way of
  importing/exporting of particular repository types. Repositories should be now a part of exported
  resources to enable automatic creation of missing repositories.
  :github:`1920`
- Added a global access condition ``has_upload_param_model_or_obj_perms`` to enforce permissions
  on the upload parameter.
  :github:`2362`
- Extended the interface of ``verify_signature`` as a new function ``gpg_verify`` to support file
  like objects in addition to a file path and also return the ``python-gnupg`` ``verify`` object.
  :github:`2930`
- Added new field ``info`` to the ``RepositoryVersion``. This will allow to store additional information for a specific version.
  :github:`2998`
- Added `pulpcore.plugin.models.EncryptedTextField to plugin api.
  :github:`3157`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Adds Master/Detail pattern overview and usage documentation to the Plugin writer docs.
  :github:`2981`
- Documented the use of ``RolesMixin`` in the plugin writer concepts section.
  :github:`3085`


Removals
~~~~~~~~

- Deprecated ``verify_signature`` in favor of ``gpg_verify`` for removal in 3.25.
  :github:`2930`


3.20.0 (2022-06-21)
===================
REST API
--------

Features
~~~~~~~~

- Added a repository filter to publications.
  :github:`1912`
- The status API endpoint now shows the python package name that provides a given plugin.
  :github:`1982`
- Queryset scoping can be customized by the user using the new field ``queryset_scoping`` on a
  ViewSet's AccessPolicy.
  :github:`2114`
- Enabled administrators to work with a customized GnuPG home directory and keyring during the
  creation of a signing service. The introduced optional arguments ``--gnupghome`` and ``--keyring``
  are available under the ``pulpcore-manager add-signing-service`` command.
  :github:`2476`
- Added the setting ``REDIRECT_TO_OBJECT_STORAGE`` to allow using cloud storage with or without
  redirecting urls.

  Added support for sftp storage via the ``pulpcore.app.models.storage.PulpSFTPStorage`` class.
  :github:`2537`
- Added more details to an error message that is shown when none of the allowed content checksums
  hashers could be used.
  :github:`2550`
- Add contains_permission query parameter to the roles API that allows clients to get back a list
  of roles that have any permission in a list of permissions.
  :github:`2715`
- Master Content endpoint, ``/pulp/api/v3/content/``, has a new access policy that allows any
  authenticated user to view content. The endpoint now scopes the content based on repositories
  the user can see.
  :github:`2724`
- New AccessPolicies have been added to ContentGuard, Distribution, Publication, Repository,
  and RepositoryVersions master ViewSets. Queryset scoping has been enabled for each ViewSet.
  :github:`2725`
- New AccessPolicy for ContentRedirectContentGuard ViewSet has been added.
  :github:`2726`
- Added dump-permissions management command to list deprecated permissions not yet translated into
  roles. This is the only way to get to this information after the 3.20 release.
  :github:`2741`
- Add ?for_object_type query parameter to Roles API that accepts an object HREF and returns a list
  of roles that only contain permissions for the given object type.
  :github:`2747`
- Add role description and permissions to group and user role serializer.
  :github:`2765`


Bugfixes
~~~~~~~~

- Leading and trailing whitespace characters are no longer trimmed in passwords within remotes.
  :github:`2068`
- Fixed generation of the redirect url to the object storage
  :github:`2075`
- Taught PulpImport to stream imports rather than reading files into memory in one chunk.

  This largely alleviates the memory-pressure that results from importing multiple
  large repositories in parallel.
  :github:`2307`
- Made the API root endpoint accessible for anonymous users once again.
  :github:`2340`
- Removed il8n from the logs written so they will always show up in English for speedy resolution of
  error messages. All user facing strings are still expected to be il8n.
  :github:`2477`
- Replaced "//" with "/" in base_url when CONTENT_PATH_PREFIX is "" or "/".
  :github:`2553`
- Fixed `does_batch` method in sync pipeline to allow waiting on content that is already resolved.
  :github:`2557`
- Fixed OOM error after uploading large chunked files.
  :github:`2573`
- Ensure downloader resets file on retry.
  :github:`2576`
- Taught PulpImport to retry more than once in the event of creation-collisions.

  This fixes a rare import-failure during high-concurrency, high-content-overlap imports.
  :github:`2589`
- Improved the error message when HTTP proxies reject requests from Pulp.
  :github:`2654`
- Fix ?ordering=role on user and group role apis so that it sorts results by role name.
  :github:`2703`
- Add options to the role_util functions to make them work the same as guardian did.
  :github:`2739`
- Fixed a bug that disallowed administrators to create a signing service via the pulpcore-manager
  utility.
  :github:`2798`
- Reduced duplicate SQL queries for ``AccessPolicy`` when accessing any view.
  :github:`2802`
- Fixed docs regarding the default for orphan protection time.
  :github:`2810`
- Started showing errors when users try to export remote artifacts.
  :github:`2817`
- Restore multiple-retry logic for PulpImport.
  :github:`2854`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Cleared out some of the paragraphs from the "Pull Request Walkthrough" section.
  :github:`1852`
- Added a troubleshooting section that includes information on how to enable DEBUG logging.
  :github:`1944`
- Removed some out of date references to Redmine (the previous issue tracker). We use Github Issues
  now.
  :github:`2642`
- Added a note about explicitly setting ``content_object`` to null when assigning model-level
  permissions.
  :github:`2758`
- Fixed ``extlinks`` use in docs to be Sphinx==5.0.0 compatible.
  :github:`2782`
- Update installation instructions about "User and database configuration" for the Database setup to point to a matching Django documentation.
  :github:`2877`


Removals
~~~~~~~~

- Removed the group permission endpoints ``api/v3/groups/:id/model_permissions/`` and
  ``api/v3/groups/:id/object_permissions/``. Permissions should be managed via roles exclusively.
  :github:`2050`
- Removed django-guardian from the stack. The ``guardian.backends.ObjectPermissionBackend`` should
  not be used anymore.
  :github:`2051`
- Deprecated creation hook interface was removed. Creation hook need to be registered with the view
  set by the plugin writer before being used. Creation hooks can no longer be added with the
  deprecated name ``permission_assignments``.
  :github:`2559`


Misc
~~~~

- :github:`2070`, :github:`2244`, :github:`2605`, :github:`2643`


Plugin API
----------

Features
~~~~~~~~

- Plugins are required to provide the ``python_package_name`` as a string attribute on their subclass
  of ``PulpPluginAppConfig``.
  :github:`1982`
- Exposed the method ``raise_for_unknown_content_units`` which raises ``ValidationError`` for content
  units that were not found in the database.
  :github:`2052`
- Plugins now have to enable default queryset scoping by setting the ``queryset_scoping`` field on the
  AccessPolicy to ``{"function": "scope_queryset"}``.

  Default queryset scoping behavior can be changed by supplying a new ``scope_queryset`` method.

  Extra queryset scoping functions can be declared on plugin ViewSets and used by setting the
  AccessPolicy's ``queryset_scoping`` field.
  :github:`2114`
- DeclarativeArtifact now accepts a ``urls`` option which permits multiple URLs
  to be provided for a single artifact. If multiple URLs are provided, the download
  stage will try each of them in turn upon encountering failures.
  :github:`2175`
- Exposed the function ``pulpcore.plugin.util.verify_signature`` for verifying signatures created
  by signing services.
  :github:`2476`
- Added ``pulpcore.plugin.content.ArtifactResponse`` to plugin API. Use this response to stream an
  artifact from the object storage if redirecting is impossible.
  :github:`2537`
- Queryset scoping is now performed when the ViewSet's AccessPolicy field ``scope_queryset`` is set to
  a function on the ViewSet.

  ``NamedModelViewSet`` now has default scoping method ``scope_queryset`` that will scope the request
  off of ``queryset_filtering_required_permission`` if present. If ViewSet is a master ViewSet then
  scoping will be performed by calling each child's scoping method if present.
  :github:`2723`
- Content ViewSets default ``scope_queryset`` method will scope based on repositories the user can see.
  :github:`2724`
- Added the ability to specify an upload for the single shot upload serializer. This allows to
  upload files in chunks and attach them with content in repositories without creating orphans.
  :github:`2786`
- Added new access condition ``has_required_repo_perms_on_upload`` for RBAC plugins to use to require
  users to specify a repository when uploading content. If not used when uploading content, non-admin
  users will not be able to see their uploaded content if queryset scoping is enabled.
  :github:`2796`


Bugfixes
~~~~~~~~

- Reworked the ordering framework to use django-filters.

  Plugins should not declare filter-backends on viewsets.
  :github:`2703`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updated plugin writers RBAC guide to explain more roles and less permissions. Removed mentions of
  django-guardian.
  :github:`2463`
- Added docs on the expectation that all user-facing strings are i8ln wrapped with gettext, but log
  messages are not.
  :github:`2477`


Removals
~~~~~~~~

- The ``pulpcore.plugin.exceptions.MissingResource`` object has been removed. Instead let 404
  errors propagate upwards for DRF to handle, or use the DRF exception ``NotFound``.
  :github:`1812`
- Removed django-guardian from the stack. This includes the removal of ``AutoDeleteObjPermsMixin``
  from the plugin api.
  :github:`2051`
- Removed the ``custom_file_object`` argument to ``pulpcore.plugin.download.BaseDownloader``. Now all
  downloaded data will be written to a random file in the current working directory. Further
  customization of where downloaded data can be written to can be done through subclassing.
  :github:`2137`
- Constructor signature of `DigestValidationError` and `SizeValidationError` has changed - the
  "actual" and "expected" values are now required and "url" which was previously a positional
  argument is now a keyword argument.
  :github:`2244`
- The pulpcore.plugin.constants.API_ROOT has been removed. Use the ``V3_API_ROOT`` and
  ``V3_API_ROOT_NO_FRONT_SLASH`` settings instead.
  :github:`2556`
- Plugins using the ``SingleArtifactContentUploadSerializer`` must place a super call when
  overwriting ``deferred_validate``. They can only assume the existance of the ``Artifact`` in the
  database, after this call.
  :github:`2786`


Misc
~~~~

- :github:`2634`, :github:`2742`


3.19.1 (2022-07-11)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Taught PulpImport to stream imports rather than reading files into memory in one chunk.

  This largely alleviates the memory-pressure that results from importing multiple
  large repositories in parallel.
  :github:`2307`
- Fixed `does_batch` method in sync pipeline to allow waiting on content that is already resolved.
  :github:`2557`
- Ensure downloader resets file on retry.
  :github:`2576`
- Taught PulpImport to retry more than once in the event of creation-collisions.

  This fixes a rare import-failure during high-concurrency, high-content-overlap imports.
  :github:`2589`
- Improved the error message when HTTP proxies reject requests from Pulp.
  :github:`2654`
- Restore multiple-retry logic for PulpImport.
  :github:`2854`
- Improve content app performance on head requests
  :github:`2924`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Removed some out of date references to Redmine (the previous issue tracker). We use Github Issues
  now.
  :github:`2642`
- Fixed ``extlinks`` use in docs to be Sphinx==5.0.0 compatible.
  :github:`2782`


Misc
~~~~

- :github:`2605`


Plugin API
----------

No significant changes.


3.19.0 (2022-04-12)
===================
REST API
--------

Features
~~~~~~~~

- Content app now logs where it gets on-demand and streamed content from.
  :github:`2059`
- Reclaim disk space can now accept ["*"] for ``repo_hrefs`` to specify all repositories for reclaim.
  :github:`2065`
- Added a filter to allow searching for user roles by their description.
  :github:`2276`
- Add swagger view and make OpenAPI human readable
  :github:`2291`
- Adds a ``TASK_DIAGNOSTICS`` setting which will enable each task to write out diagnostic information
  such as memory usage of the task to a data file in ``/var/tmp/pulp/<task_UUID>/``. This is disabled
  by default.
  :github:`2329`
- Added a ``/pulp/api/v3/distributions/`` endpoint to list all distributions.
  :github:`2379`


Bugfixes
~~~~~~~~

- Added reason for 404 error when accessing distributions without a publication.
  :github:`1910`
- Fixed validation order of required settings to occur before plugin settings are loaded.
  :github:`1968`
- Fix delete repository version causing "duplicate key value violates unique constraint" error.
  :github:`2047`
- Fixed two instances of Pulp not writing to the task worker's temporary directory.
  :github:`2061`
- Reduced memory usage during tasks like sync by holding fewer objects in-memory unnecessarily.
  :github:`2069`
- Fixed migration 0064_add_new_style_task_columns to purge extraneous ReservedResource and
  TaskReservedResource entries, which could block sync and publish tasks post-upgrade.

  Also taught the migration to bulk-update the Task changes. In large installations, this
  should have a positive impact on the time it takes to apply the migration.
  :github:`2101`
- Taught task-purge to process tasks in batches of 1000. This prevents large purges from using
  large amounts of memory as a result of reading all the affected Tasks into memory at once.
  :github:`2215`
- This fix prevents the lost track of a content removed version when deleting a repository version that deletes a content that is added back in the subsequent version, but deleted again in a later version.
  :github:`2267`
- Added transactions around repository version operations to prevent data loss.
  :github:`2268`
- Loosened the version-restrictions on PulpImport to only require X.Y matching.
  :github:`2269`
- Fix a mistake in a previous migration which may have caused improperly encrypted remote fields.
  :github:`2327`
- Fixed improper fields being listed in ``RepositoryVersion`` repair API.
  :github:`2330`
- Fixes duplicate key error ``Key (content_artifact_id, remote_id)`` when creating ``RemoteArtifacts``
  during syncs in pulp_container and possibly other plugins.
  :github:`2381`
- Declared proper dependency on user model in migration 0040.
  :github:`2403`
- Fixed a rare deadlock when sync'ing overlapping content in high-concurrency envs.
  :github:`2420`
- Fixed a (rare) deadlock around bulk_update() during syncs with overlapping content.
  :github:`2430`
- Fixed a bug where notifications to workers may go unnoticed. This may lead to idle workers while
  there are tasks waiting.
  :github:`2506`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updates and revises docs on webserver based authentication.
  :github:`2260`
- Adds docs on recording and building graphs from the memory data saved by the ``TASK_DIAGNOSTICS``
  setting.
  :github:`2329`


Removals
~~~~~~~~

- Removed the Django UI Admin site. It was added to provide RBAC permissions management before there
  were APIs that could provide that. It was tech preview and now there are APIs for user and group
  management, along with role and permission assignment. It is being removed because the direct DB
  access it provides has caused some issues for users, especially since its not integrated with the
  validation provided by Django Rest Framework, which Pulp uses.
  :github:`2374`


Plugin API
----------

Features
~~~~~~~~

- Exposed the ``PulpRemoteUserAuthentication`` class to plugin writers. This will allow the use of
  remote authentication methods when building protected endpoints.
  :github:`2262`
- Added new global access conditions ``has_publication_param_model_or_obj_perms`` and
  ``has_repo_or_repo_ver_param_model_or_obj_perms`` for RBAC checks.
  :github:`2364`
- Changed the ``reusable_conditions`` module configuration for access policies to being a list to
  enable plugins to add custom modules to it.
  :github:`2495`


Bugfixes
~~~~~~~~

- Adjusted the default size of the queues between pipelines to be 1 instead of 1000. The batchers in
  the stage will still accumulate up to 500 (by default) items so batching is still in-effect there
  where it matters.
  :github:`2069`


3.18.11 (2022-11-02)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed the fs exporter to handle the case where there are pre-existing files in the location that FileSystem attempts to export to you get a FileExistsError.
  :github:`1949`
- Fixed the fs exporter to handle the case where hardlink method was requested but pulp and export locations are in different partitions so can't share the same inode.
  :github:`3187`
- Another step on closing the deadlock-window when syncing overlapping content.
  :github:`3284`


Plugin API
----------

No significant changes.


3.18.10 (2022-09-14)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Another guardrail added around content-stages to address deadlock in a specific usecase.
  :github:`3192`


Plugin API
----------

No significant changes.


3.18.9 (2022-09-01)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed the value of the Content-Type header returned for .xml.gz files.
  :github:`2811`
- Fixed another rare deadlock for high-concurrency/overlapping-content syncs.
  :github:`3111`


Plugin API
----------

No significant changes.


3.18.8 (2022-08-16)
===================
REST API
--------

No significant changes.


Plugin API
----------

No significant changes.


3.18.7 (2022-08-15)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Serialized orphan cleanup tasks with respect to each other to prevent them from failing.
  :github:`3030`


Plugin API
----------

No significant changes.


3.18.6 (2022-08-03)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Restore multiple-retry logic for PulpImport.
  :github:`2854`
- Improve content app performance on head requests
  :github:`2924`
- Use published relative paths for FS Exporter.
  :github:`2933`
- Configured aiohttp to avoid rewriting redirect URLs, as some web servers (e.g. Amazon CloudFront) can be tempermental about the encoding of the URL.
  :github:`2964`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Removed some out of date references to Redmine (the previous issue tracker). We use Github Issues
  now.
  :github:`2642`
- Fixed ``extlinks`` use in docs to be Sphinx==5.0.0 compatible.
  :github:`2782`


Plugin API
----------

No significant changes.


3.18.5 (2022-05-10)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Taught PulpImport to stream imports rather than reading files into memory in one chunk.

  This largely alleviates the memory-pressure that results from importing multiple
  large repositories in parallel.
  :github:`2307`
- Fixed `does_batch` method in sync pipeline to allow waiting on content that is already resolved.
  :github:`2557`
- Ensure downloader resets file on retry.
  :github:`2576`
- Taught PulpImport to retry more than once in the event of creation-collisions.

  This fixes a rare import-failure during high-concurrency, high-content-overlap imports.
  :github:`2589`
- Improved the error message when HTTP proxies reject requests from Pulp.
  :github:`2654`


Plugin API
----------

No significant changes.


3.18.4 (2022-04-12)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed two instances of Pulp not writing to the task worker's temporary directory.
  :github:`2061`
- Taught task-purge to process tasks in batches of 1000. This prevents large purges from using
  large amounts of memory as a result of reading all the affected Tasks into memory at once.
  :github:`2215`
- Loosened the version-restrictions on PulpImport to only require X.Y matching.
  :github:`2269`
- Fixed a (rare) deadlock around bulk_update() during syncs with overlapping content.
  :github:`2430`
- Fixed a bug where notifications to workers may go unnoticed. This may lead to idle workers while
  there are tasks waiting.
  :github:`2506`


Plugin API
----------

No significant changes.


3.18.3 (2022-03-25)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Reduced memory usage during tasks like sync by holding fewer objects in-memory unnecessarily.
  :github:`2069`
- Fixes duplicate key error ``Key (content_artifact_id, remote_id)`` when creating ``RemoteArtifacts``
  during syncs in pulp_container and possibly other plugins.
  :github:`2381`
- Declared proper dependency on user model in migration 0040.
  :github:`2403`
- Fixed a rare deadlock when sync'ing overlapping content in high-concurrency envs.
  :github:`2420`


Plugin API
----------

Bugfixes
~~~~~~~~

- Adjusted the default size of the queues between pipelines to be 1 instead of 1000. The batchers in
  the stage will still accumulate up to 500 (by default) items so batching is still in-effect there
  where it matters.
  :github:`2069`


3.18.2 (2022-03-18)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix delete repository version causing "duplicate key value violates unique constraint" error.
  :github:`2047`
- Fixed migration 0064_add_new_style_task_columns to purge extraneous ReservedResource and
  TaskReservedResource entries, which could block sync and publish tasks post-upgrade.

  Also taught the migration to bulk-update the Task changes. In large installations, this
  should have a positive impact on the time it takes to apply the migration.
  :github:`2101`
- This fix prevents the lost track of a content removed version when deleting a repository version that deletes a content that is added back in the subsequent version, but deleted again in a later version.
  :github:`2267`
- Fix a mistake in a previous migration which may have caused improperly encrypted remote fields.
  :github:`2327`


Plugin API
----------

No significant changes.


3.18.1 (2022-03-01)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Added transactions around repository version operations to prevent data loss.
  :github:`2268`


Plugin API
----------

No significant changes.


3.18.0 (2022-02-22)
===================
REST API
--------

Features
~~~~~~~~

- Added a pulpcore-manager command `remove-plugin` to remove a Pulp plugin.
  :github:`1945`
- Implemented the Redis caching machinery that can be used within the synchronous context.
  :github:`2003`
- Add a "current_task" field to workers so that you can easily see which workers are currently active.
  :github:`2034`
- Allowed Pulp to install without Redis.
  :github:`2057`
- Added ``has_repository_obj_perms`` and ``has_repository_model_or_obj_perms`` as access conditions
  that can be used by viewsets nested beneath repository viewsets.
  :github:`2076`
- Queryset scoping can now be disabled by changing the ``DEFAULT_PERMISSION_CLASSES``.
  :github:`2115`
- Specifying a different value for ``DEFAULT_PERMISSION_CLASSES`` will now automatically disable the
  permission assignment provided by the ``creation_hooks`` portion of an ``AccessPolicyFromDB``.
  :github:`2116`
- The Pulp API can now be rerooted using the new ``API_ROOT`` setting. By default it is set to
  ``/pulp/``. Pulp appends the string ``api/v3/`` onto the value of ``API_ROOT``.
  :github:`2148`
- Added a redirecting content guard that can be employed by plugins to forward from a REST call to
  the content app.
  :github:`2151`
- Added a new `analyze-publication` management command to facilitate debugging.
  :github:`2200`
- Added a read-only task schedule view for configured tasks schedules.

  NOTE: This feature is in tech-preview and may change in backwards incompatible ways in the future.
  :github:`2204`


Bugfixes
~~~~~~~~

- Fix import and export OOM error.
  :github:`2072`
- Fixed downloader retry logic with partially written files.
  :github:`2078`
- Fix content summary showing incorrect count after previous version deletion.
  :github:`2084`
- Fixed issue with listing repository versions after deleting previous versions.
  :github:`2085`
- Fixed file descriptior leak during upload.
  :github:`2087`
- Fixed an api schema bug where both ``permission_assignment`` and ``creation_hooks`` were required
  by the ``AccessPolicy`` serializer.
  :github:`2089`
- Fixed migration 0081 to be compatible with custom User models.
  :github:`2090`
- Fixed PulpImport to correctly save relative to MEDIA_ROOT.
  :github:`2091`
- Added proper logging around certain ways a task could fail.
  :github:`2093`
- Taught PulpImport to retry in the event of a concurrency-collision on ContentArtifact.
  :github:`2102`
- Fixed an edge case where the first (streamed) response from an repo synced as "on_demand" could be incorrect.
  :github:`2119`
- Fixed bug where retries of partially downloaded files failed digest and size validation.
  :github:`2135`
- Fixed the calculation of response range headers in streaming answers from the content app.
  :github:`2147`
- Fixed potential deadlock-window in touch() path.
  :github:`2157`
- Fixed reporting tasks being canceled before being picked up by a worker as canceled instead of
  failed.
  :github:`2183`
- Return a concise message exception on 500 in case file is missing on the FS.
  :github:`2187`
- Fixed import/export of repositories with sub-content.

  An example would be the sub-repositories in pulp_rpm
  DistributionTrees.
  :github:`2192`
- touch() now uses standard Django instead of raw-sql to update.
  :github:`2229`


Misc
~~~~

- :github:`2086`, :github:`2094`, :github:`2173`, :github:`2202`


Plugin API
----------

Features
~~~~~~~~

- The ``AutoAddObjPermsMixin`` now calls a ``handle_creation_hooks`` interface on the configured DRF
  permission class, e.g. the default ``AccessPolicyFromDB``.
  :github:`2116`
- Added a redirecting content guard that can be employed by plugins to generate preauthenticated URLs
  that forward from a REST call to the content app. Added the ``GetOrCreateSerializerMixin`` to
  ``get_or_create`` objects still validating them through the serializer.
  :github:`2151`
- Exposed synchronous and asynchronous caching machinery. The classes ``AsyncContentCache`` and
  ``SyncContentCache`` can be now managed by plugin writers.
  :github:`8806`


Bugfixes
~~~~~~~~

- Started using a plugin provided serializer in `has_remote_param_obj_perms` and
  `has_remote_param_model_or_obj_perms` to solve the `Unexpected field` error during sync by
  a non-admin user.
  :github:`2088`
- Exposed adjust_roles in the plugin api.
  :github:`2092`
- Expose Roles model in plugin api.
  :github:`2185`


Removals
~~~~~~~~

- Deprecate the the use of ``custom_file_object`` parameter in ``BaseDownloader``.
  :github:`2123`


Deprecations
~~~~~~~~~~~~

- The ``API_ROOT`` constant has been deprecated and turned into a setting. Its removal is scheduled
  for 3.20. Please use the setting with the same name instead.
  :github:`2148`
- The ``ACCESS_POLICY_VIEWSET_NAME`` attribute is no longer expected to be present on models. The
  RBAC machinery no longer uses this, and if present a deprecation warning will be emitted.
  :github:`2209`


3.17.8 (2022-05-10)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Taught PulpImport to stream imports rather than reading files into memory in one chunk.

  This largely alleviates the memory-pressure that results from importing multiple
  large repositories in parallel.
  :github:`2307`
- Fixed `does_batch` method in sync pipeline to allow waiting on content that is already resolved.
  :github:`2557`
- Ensure downloader resets file on retry.
  :github:`2576`
- Taught PulpImport to retry more than once in the event of creation-collisions.

  This fixes a rare import-failure during high-concurrency, high-content-overlap imports.
  :github:`2589`
- Improved the error message when HTTP proxies reject requests from Pulp.
  :github:`2654`


Plugin API
----------

No significant changes.


3.17.7 (2022-04-12)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed two instances of Pulp not writing to the task worker's temporary directory.
  :github:`2061`
- Taught task-purge to process tasks in batches of 1000. This prevents large purges from using
  large amounts of memory as a result of reading all the affected Tasks into memory at once.
  :github:`2215`
- Loosened the version-restrictions on PulpImport to only require X.Y matching.
  :github:`2269`
- Fixed a (rare) deadlock around bulk_update() during syncs with overlapping content.
  :github:`2430`
- Fixed a bug where notifications to workers may go unnoticed. This may lead to idle workers while
  there are tasks waiting.
  :github:`2506`


Plugin API
----------

No significant changes.


3.17.6 (2022-03-25)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Reduced memory usage during tasks like sync by holding fewer objects in-memory unnecessarily.
  :github:`2069`
- Fixes duplicate key error ``Key (content_artifact_id, remote_id)`` when creating ``RemoteArtifacts``
  during syncs in pulp_container and possibly other plugins.
  :github:`2381`
- Declared proper dependency on user model in migration 0040.
  :github:`2403`
- Fixed a rare deadlock when sync'ing overlapping content in high-concurrency envs.
  :github:`2420`


Plugin API
----------

Bugfixes
~~~~~~~~

- Adjusted the default size of the queues between pipelines to be 1 instead of 1000. The batchers in
  the stage will still accumulate up to 500 (by default) items so batching is still in-effect there
  where it matters.
  :github:`2069`


3.17.5 (2022-03-18)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix delete repository version causing "duplicate key value violates unique constraint" error.
  :github:`2047`
- Fixed migration 0064_add_new_style_task_columns to purge extraneous ReservedResource and
  TaskReservedResource entries, which could block sync and publish tasks post-upgrade.

  Also taught the migration to bulk-update the Task changes. In large installations, this
  should have a positive impact on the time it takes to apply the migration.
  :github:`2101`
- Taught PulpImport to retry in the event of a concurrency-collision on ContentArtifact.
  :github:`2102`
- This fix prevents the lost track of a content removed version when deleting a repository version that deletes a content that is added back in the subsequent version, but deleted again in a later version.
  :github:`2267`
- Fix a mistake in a previous migration which may have caused improperly encrypted remote fields.
  :github:`2327`


Plugin API
----------

No significant changes.


3.17.4 (2022-03-01)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix import and export OOM error.
  :github:`2072`
- Fixed downloader retry logic with partially written files.
  :github:`2078`
- Fix content summary showing incorrect count after previous version deletion.
  :github:`2084`
- Fixed issue with listing repository versions after deleting previous versions.
  :github:`2085`
- Fixed file descriptior leak during upload.
  :github:`2087`
- Added proper logging around certain ways a task could fail.
  :github:`2093`
- Make checksum mismatches a retryable error.
  :github:`2094`
- Fixed an edge case where the first (streamed) response from an repo synced as "on_demand" could be incorrect.
  :github:`2119`
- Fixed bug where retries of partially downloaded files failed digest and size validation.
  :github:`2135`
- Fixed the calculation of response range headers in streaming answers from the content app.
  :github:`2147`
- Fixed potential deadlock-window in touch() path.
  :github:`2157`
- Fixed reporting tasks being canceled before being picked up by a worker as canceled instead of
  failed.
  :github:`2183`
- Fixed import/export of repositories with sub-content.

  An example would be the sub-repositories in pulp_rpm
  DistributionTrees.
  :github:`2192`
- touch() now uses standard Django instead of raw-sql to update.
  :github:`2229`
- Added transactions around repository version operations to prevent data loss.
  :github:`2268`


Plugin API
----------

No significant changes.


3.17.3 (2022-01-12)
===================
REST API
--------

No significant changes.


Plugin API
----------

Bugfixes
~~~~~~~~

- Exposed adjust_roles in the plugin api.
  (backported from #9665)
  :redmine:`9668`


3.17.2 (2022-01-06)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed PulpImport to correctly save relative to MEDIA_ROOT.
  (backported from #9660)
  :redmine:`9664`


Plugin API
----------

No significant changes.


3.17.1 (2021-12-21)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed migration 0081 to be compatible with custom User models.
  :redmine:`9654`


Plugin API
----------

No significant changes.


3.17.0 (2021-12-14)
===================
REST API
--------

Features
~~~~~~~~

- Added a ``/tasks/purge/`` API to do bulk-deletion of old tasks.

  Over time, the database can fill with task-records. This API allows
  an installation to bulk-remove records based on their completion
  timestamps.

  NOTE: this endpoint is in tech-preview and may change in backwards
  incompatible ways in the future.
  :redmine:`8554`
- Added a role model to support RBAC and the utility functions ``assign_role`` and ``remove_role``.

  The field ``permissions_assignment`` of access policies has been renamed to ``creation_hooks``. A
  compatibility patch has been added to be removed with pulpcore=3.20.

  The ``permissions`` argument to ``creation_hooks`` has been deprecated to be removed with
  pulpcore=3.20.
  :redmine:`9411`
- Added views to assign model and object level roles to users and groups.
  :redmine:`9413`
- Rewrote existing access policies on viewsets to use roles.
  :redmine:`9415`
- Added validation to prevent credentials in remote urls. Also added data migration to move
  credentials out of remote url and into remote username/password fields for existing remotes.
  :redmine:`9459`
- Reworked RBAC Content Guards to now use roles. Added new endpoints ``{list, add, remove}_roles`` and ``my_permissions`` to the RBAC content guard viewset.
  :redmine:`9498`
- Content-type and Content-disposition headers are now sent in the AzureStorage.url.
  :redmine:`9518`
- SigningService scripts can now access the public key fingerprint using the ``PULP_SIGNING_KEY_FINGERPRINT`` environment variable.
  This allows for more generic scripts, that do not need to "guess" (hardcode) what key they should use.
  :redmine:`9532`
- Added object specific endpoints ``{list,add}_roles``, ``remove_roles`` and ``my_permissions`` to tasks and groups viewsets.
  :redmine:`9604`
- Added a ``reset`` endpoint to the access policy viewset to revert to the provided default uncustomized access policy.
  :redmine:`9606`


Bugfixes
~~~~~~~~

- PulpImporter now unpacks into the task-worker's working directory rather than /tmp. Unpacking
  large files into /tmp could cause the operation to fail, or even cause stability issues for
  Pulp instance, due to running /tmp out of space.
  :redmine:`8610`
- Missing worker records are now kept in the database for seven days allowing time for post-mortem
  analysis of them. The user-facing data in the status API remains unmodified.
  :redmine:`8988`
- Made Pulp to be fault-tolerant to Redis server connection issues.
  :redmine:`8997`
- Cache is now properly invalidated after reclaim disk task.
  :redmine:`9215`
- Fixed bug where the content app would stop working after a brief loss of connection to the database.
  :redmine:`9276`
- Improved messaging around timeout requests.
  :redmine:`9301`
- Updated the distribution validation to properly handle the use of ``repository`` / ``repository_version`` / ``publication``.
  :redmine:`9434`
- Fixed issue with listing repository versions while running orphan cleanup task.
  :redmine:`9481`
- Fixed erroneous ordering filters from appearing in HTML views and causing 500 errors when used.
  :redmine:`9496`
- Fixed bug where Artifacts were being downloaded even if they were already saved in Pulp.
  :redmine:`9542`
- Fixed a bug in pulpcore-worker, where wakeup and cancel signals could be lost due to a race
  condition.
  :redmine:`9549`
- Fixed bug where chunked uploads were being assembled in /tmp.
  :redmine:`9550`
- Created a proxy model for Groups to allow using creation_hooks with them.
  :redmine:`9588`
- Fixed permission errors on artifact retrieval from object storage when redis caching is enabled.
  :redmine:`9595`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Adjusted the RBAC documentation for the roles framework.
  :redmine:`9411`
- Added documentation for ``DB_ENCRYPTION_KEY`` setting.
  :redmine:`9495`
- Fixed the path to uploaded artifacts.
  :redmine:`9527`


Removals
~~~~~~~~

- The ``pulpcore-worker`` binary no longer accepts the ``--resource-manager`` flag. There is no
  resource manager anymore, so this flag is no longer needed.
  :redmine:`9327`
- Removed tech previewed ``assign_permission`` and ``remove_permission`` endpoints from RBAC content guard viewset.
  :redmine:`9498`


Misc
~~~~

- :redmine:`9353`, :redmine:`9354`, :redmine:`9506`


Plugin API
----------

Features
~~~~~~~~

- Added ``get_objects_for_user`` to support queryset filtering by roles.
  Added hooks in ``AutoAddObjPermsMixin`` to support auto-assignment of roles.

  Changed the lookup for creation hooks so hooks need to be registered in
  ``REGISTERED_CREATION_HOOKS`` on the model to be used. The signature for creation hooks that are
  registered must match the exploded version of the dict parameters from the access policy.
  Unregistered creation hooks are deprecated and support will be dropped in pulpcore 3.20.
  :redmine:`9411`
- Made RepositoryAddRemoveContentSerializer available for plugin writers.
  :redmine:`9504`
- Added ability to pass headers through the AzureStorage.url.
  :redmine:`9518`
- ``Remote.get_remote_artifact_url`` now accepts a ``request`` parameter.
  :redmine:`9554`
- Added ``initialize_new_version`` function to ``Repository`` model.
  :redmine:`9579`
- `DownloaderFactory.user_agent()` method is now available if plugin needs to generate User-Agent header value to use in their custom (subclasssed) downloader factory.
  :redmine:`9591`
- Added ability to use a custom download factory. `Remote.get_downloader` now accepts a `download_factory` parameter.
  :redmine:`9592`
- ``Handler._serve_content_artifact`` method accepts new positional argument ``request``.
  :redmine:`9595`
- Added Group model to plugin api.
  Added ``RolesMixin`` to for viewsets to allow managing object roles based on permissions.
  :redmine:`9604`
- Added new async sign method ``asign`` to the ``SigningService`` model.
  :redmine:`9615`
- ``SigningService.sign`` and ``SigningService.asign`` now accepts a ``env_var`` parameter that makes
  it possible to pass environment variables to the signing script.
  :redmine:`9621`


Bugfixes
~~~~~~~~

- Include additional information about which AccessPolicy is using deprecated policy features.
  :redmine:`9608`


3.16.15 (2022-11-02)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed the fs exporter to handle the case where there are pre-existing files in the location that FileSystem attempts to export to you get a FileExistsError.
  :github:`1949`
- Fixed the fs exporter to handle the case where hardlink method was requested but pulp and export locations are in different partitions so can't share the same inode.
  :github:`3187`
- Another step on closing the deadlock-window when syncing overlapping content.
  :github:`3284`


Plugin API
----------

No significant changes.


3.16.14 (2022-09-13)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed the value of the Content-Type header returned for .xml.gz files.
  :github:`2811`
- Another guardrail added around content-stages to address deadlock in a specific usecase.
  :github:`3192`


Plugin API
----------

No significant changes.


3.16.13 (2022-09-01)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed another rare deadlock for high-concurrency/overlapping-content syncs.
  :github:`3111`


Plugin API
----------

No significant changes.


3.16.12 (2022-08-05)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Use published relative paths for FS Exporter.
  :github:`2933`
- Serialized orphan cleanup tasks with respect to each other to prevent them from failing.
  :github:`3030`


Plugin API
----------

No significant changes.


3.16.11 (2022-07-14)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Improve content app performance on head requests
  :github:`2924`
- Configured aiohttp to avoid rewriting redirect URLs, as some web servers (e.g. Amazon CloudFront) can be tempermental about the encoding of the URL.
  :github:`2964`


Plugin API
----------

No significant changes.


3.16.10 (2022-06-16)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Restore multiple-retry logic for PulpImport.
  :github:`2854`


Plugin API
----------

No significant changes.


3.16.9 (2022-06-15)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Started showing errors when users try to export remote artifacts.
  :github:`2817`


Misc
~~~~

- :github:`2816`


Plugin API
----------

No significant changes.


3.16.8 (2022-05-10)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Taught PulpImport to stream imports rather than reading files into memory in one chunk.

  This largely alleviates the memory-pressure that results from importing multiple
  large repositories in parallel.
  :github:`2307`
- Fixed `does_batch` method in sync pipeline to allow waiting on content that is already resolved.
  :github:`2557`
- Ensure downloader resets file on retry.
  :github:`2576`
- Taught PulpImport to retry more than once in the event of creation-collisions.

  This fixes a rare import-failure during high-concurrency, high-content-overlap imports.
  :github:`2589`
- Improved the error message when HTTP proxies reject requests from Pulp.
  :github:`2654`


Plugin API
----------

No significant changes.


3.16.7 (2022-04-12)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed two instances of Pulp not writing to the task worker's temporary directory.
  :github:`2061`
- Fixed file descriptior leak during upload.
  :github:`2087`
- Fixed a bug in pulpcore-worker, where wakeup and cancel signals could be lost due to a race
  condition.
  :github:`2144`
- Loosened the version-restrictions on PulpImport to only require X.Y matching.
  :github:`2269`
- Fixed a (rare) deadlock around bulk_update() during syncs with overlapping content.
  :github:`2430`
- Fixed a bug where notifications to workers may go unnoticed. This may lead to idle workers while
  there are tasks waiting.
  :github:`2506`


Plugin API
----------

No significant changes.


3.16.6 (2022-03-25)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Reduced memory usage during tasks like sync by holding fewer objects in-memory unnecessarily.
  :github:`2069`
- Fixes duplicate key error ``Key (content_artifact_id, remote_id)`` when creating ``RemoteArtifacts``
  during syncs in pulp_container and possibly other plugins.
  :github:`2381`
- Declared proper dependency on user model in migration 0040.
  :github:`2403`
- Fixed a rare deadlock when sync'ing overlapping content in high-concurrency envs.
  :github:`2420`
- Fixed secure proxy support by updating aiohttp version to ~=3.8.1.
  :github:`2423`


Plugin API
----------

Bugfixes
~~~~~~~~

- Adjusted the default size of the queues between pipelines to be 1 instead of 1000. The batchers in
  the stage will still accumulate up to 500 (by default) items so batching is still in-effect there
  where it matters.
  :github:`2069`


3.16.5 (2022-03-17)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix delete repository version causing "duplicate key value violates unique constraint" error.
  :github:`2047`
- Fixed migration 0064_add_new_style_task_columns to purge extraneous ReservedResource and
  TaskReservedResource entries, which could block sync and publish tasks post-upgrade.

  Also taught the migration to bulk-update the Task changes. In large installations, this
  should have a positive impact on the time it takes to apply the migration.
  :github:`2101`
- Taught PulpImport to retry in the event of a concurrency-collision on ContentArtifact.
  :github:`2102`
- This fix prevents the lost track of a content removed version when deleting a repository version that deletes a content that is added back in the subsequent version, but deleted again in a later version.
  :github:`2267`
- Fix a mistake in a previous migration which may have caused improperly encrypted remote fields.
  :github:`2327`


Plugin API
----------

No significant changes.


3.16.4 (2022-03-01)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix content summary showing incorrect count after previous version deletion.
  :github:`2084`
- Fixed issue with listing repository versions after deleting previous versions.
  :github:`2085`
- Fixed potential deadlock-window in touch() path.
  :github:`2157`
- Fixed import/export of repositories with sub-content.

  An example would be the sub-repositories in pulp_rpm
  DistributionTrees.
  :github:`2192`
- touch() now uses standard Django instead of raw-sql to update.
  :github:`2229`
- PulpImporter now unpacks into the task-worker's working directory rather than /tmp. Unpacking
  large files into /tmp could cause the operation to fail, or even cause stability issues for
  Pulp instance, due to running /tmp out of space.
  :github:`2247`
- Added transactions around repository version operations to prevent data loss.
  :github:`2268`


Plugin API
----------

No significant changes.


3.16.3 (2022-02-08)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix import and export OOM error.
  :github:`2072`
- Fixed downloader retry logic with partially written files.
  :github:`2078`
- Fixed bug where retries of partially downloaded files failed digest and size validation.
  :github:`2135`
- Fixed the calculation of response range headers in streaming answers from the content app.
  :github:`2147`
- Improved messaging around timeout requests.
  :github:`2169`
- Fixed reporting tasks being canceled before being picked up by a worker as canceled instead of
  failed.
  :github:`2183`


Misc
~~~~

- :github:`2094`


Plugin API
----------

No significant changes.


3.16.2 (2022-01-07)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed PulpImport to correctly save relative to MEDIA_ROOT.
  (backported from #9660)
  :redmine:`9663`


Plugin API
----------

No significant changes.


3.16.1 (2021-12-02)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed bug where Artifacts were being downloaded even if they were already saved in Pulp.
  (backported from #9542)
  :redmine:`9596`
- Fixed bug where the content app would stop working after a brief loss of connection to the database.
  (backported from #9276)
  :redmine:`9598`


Plugin API
----------

No significant changes.


3.16.0 (2021-10-05)
===================
REST API
--------

Features
~~~~~~~~

- Prioritize remote content provided by Alternate Content Sources over regular content in the content
  app.
  :redmine:`8749`
- Marked readonly task resources as shared for concurrent use.
  :redmine:`9326`
- Added validation for the remote type that can be used with the ACS.
  :redmine:`9375`


Bugfixes
~~~~~~~~

- Ordered several ContentStages paths to fix deadlocks in high-concurrency scenarios.
  :redmine:`8750`
- Fixed a bug where ``pulpcore-content`` decompressed data while incorrectly advertising to clients
  it was still compressed via the ``Content-Encoding: gzip`` header.
  :redmine:`9213`
- Changed the pulpcore-worker to mark abandoned tasks as "failed" instead of "canceled".
  :redmine:`9247`
- Fixed the repository modify endpoint performance problems.
  :redmine:`9266`
- ``RBACContentGuard`` assign/remove permission endpoints now properly return 201 instead of 200
  :redmine:`9314`
- Fixed bug where some Openshift environments could not start workers due to a strange Python runtime
  import issue.
  :redmine:`9338`
- PATCH/PUT/DELETE calls for the ACS are asynchronous and trigger a task.
  :redmine:`9374`
- Fixed update call for the ACS so paths are not silenty removed when other fields are being updated.
  :redmine:`9376`
- Fixed an issue where on_demand content might not be downloaded properly if the remote URL was changed (even if re-synced).
  :redmine:`9395`
- Fixed a bug, where natural key calculations on content performed superfluous database calls.
  :redmine:`9409`
- Ensured that with the removal of ACS its' hidden repositories are removed as well.
  :redmine:`9417`
- Taught a remote-artifact error path to not assume 'filename' was valid for all content.
  :redmine:`9427`
- Taught several more codepaths to order-before-update to avoid deadlocks.
  :redmine:`9441`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added an architecture diagram to the components page.
  :redmine:`7692`
- Fixed a note saying where to find versioning details.
  :redmine:`8859`
- Removed deprecated uses of ``MEDIA_ROOT``.
  :redmine:`9100`
- Updated ACS docs to use CLI commands.
  :redmine:`9251`
- Document Azure storage needs to set ``MEDIA_ROOT``
  :redmine:`9428`
- Corrected a fact that Redis is needed by the tasking system in the installation section.
  :redmine:`9436`


Removals
~~~~~~~~

- Removed the legacy tasking system and the ``USE_NEW_WORKER_TYPE`` setting.
  :redmine:`9157`
- Removed OpenAPI browsable API
  :redmine:`9322`
- Updated the pulp import creation endpoint to return a task group instead of a task.
  :redmine:`9382`


Misc
~~~~

- :redmine:`9432`, :redmine:`9443`


Plugin API
----------

Features
~~~~~~~~

- Added optional stage for Alternate Content Source support.
  :redmine:`8748`
- ``AlternateContentSource`` has a new class variable ``REMOTE_TYPES`` that it will use to validate
  the type of remote set on the ACS.
  :redmine:`9375`
- Added ``pulpcore.plugin.viewset.TaskGroupResponse`` which can be used to return a reference to a
  task group created in a viewset. Added ``pulpcore.plugin.serializers.TaskGroupResponseSerializer``
  which can be used to indicate the serializer response format of viewsets that will use
  ``TaskGroupResponse`` similar to how ``AsyncOperationResponseSerializer`` is used.
  :redmine:`9380`
- Added the ``pulpcore.plugin.tasking.general_multi_delete`` that deletes a list of model instances
  in a transaction.
  :redmine:`9417`
- Exposed tasks ``general_create``, ``general_create_from_temp_file``, ``general_delete``,
  ``general_update``, ``orphan_cleanup``, and ``reclaim_space`` in the plugin api.
  :redmine:`9418`
- `ALLOW_SHARED_TASK_RESOURCES` is now enabled by default.  If all goes smoothly, this will become permanent and the setting will be removed in the next release.
  :redmine:`9474`


Bugfixes
~~~~~~~~

- Set the default widget type to ``JSONWidget`` for ``JSONFields`` for Model Resources to fix
  django-import-export bug where ``django.db.models.JSONFields`` weren't properly handled.
  :redmine:`9307`
- PATCH/PUT/DELETE calls for the ACS are asynchronous and trigger a task.
  :redmine:`9374`


Removals
~~~~~~~~

- Removed the deprecated ``reserved_resources_record__resource`` filter for Task. Use
  ``reserved_resources_record__contains`` instead.
  :redmine:`9157`
- Removed drf-access-policy workaround for condition/condition_expession.
  :redmine:`9163`
- Removed ACS path validation. Plugins should now define ``validate_paths`` on their ACS serializer to
  validate paths.
  :redmine:`9340`
- Renamed ``TaskGroupResponse`` to ``TaskGroupOperationResponse`` and ``TaskGroupResponseSerializer``
  to ``TaskGroupOperationResponseSerializer`` in order to avoid conflicts with responses from task
  groups endpoints.
  :redmine:`9425`
- The `resources` argument of `dispatch()` has been removed. `exclusive_resources` and `shared_resources` should be used instead.
  :redmine:`9477`
- ContentSaver._pre_save() and ContentSaver._post_save() must now be implemented as synchronous functions rather than coroutines.
  :redmine:`9478`



3.15.9 (2022-06-28)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Restore multiple-retry logic for PulpImport.
  :github:`2854`


Misc
~~~~

- :github:`2856`


Plugin API
----------

No significant changes.


3.15.8 (2022-04-12)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed file descriptior leak during upload.
  :github:`2087`
- Fixed a bug in pulpcore-worker, where wakeup and cancel signals could be lost due to a race
  condition.
  :github:`2144`
- Fixed a bug where notifications to workers may go unnoticed. This may lead to idle workers while
  there are tasks waiting.
  :github:`2506`
- Changed the pulpcore-worker to mark abandoned tasks as "failed" instead of "canceled".
  :github:`2532`


Plugin API
----------

No significant changes.


3.15.7 (2022-03-25)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Reduced memory usage during tasks like sync by holding fewer objects in-memory unnecessarily.
  :github:`2069`
- Fixes duplicate key error ``Key (content_artifact_id, remote_id)`` when creating ``RemoteArtifacts``
  during syncs in pulp_container and possibly other plugins.
  :github:`2381`
- Declared proper dependency on user model in migration 0040.
  :github:`2403`
- Fixed a rare deadlock when sync'ing overlapping content in high-concurrency envs.
  :github:`2420`


Plugin API
----------

Bugfixes
~~~~~~~~

- Adjusted the default size of the queues between pipelines to be 1 instead of 1000. The batchers in
  the stage will still accumulate up to 500 (by default) items so batching is still in-effect there
  where it matters.
  :github:`2069`


3.15.6 (2022-03-22)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix a mistake in a previous migration which may have caused improperly encrypted remote fields.
  :github:`2327`


Plugin API
----------

No significant changes.


3.15.5 (2022-03-15)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fix delete repository version causing "duplicate key value violates unique constraint" error.
  :github:`2047`
- Fix content summary showing incorrect count after previous version deletion.
  :github:`2084`
- Fixed issue with listing repository versions after deleting previous versions.
  :github:`2085`
- Fixed migration 0064_add_new_style_task_columns to purge extraneous ReservedResource and
  TaskReservedResource entries, which could block sync and publish tasks post-upgrade.

  Also taught the migration to bulk-update the Task changes. In large installations, this
  should have a positive impact on the time it takes to apply the migration.
  :github:`2101`
- Taught PulpImport to retry in the event of a concurrency-collision on ContentArtifact.
  :github:`2102`
- Fixed potential deadlock-window in touch() path.
  :github:`2157`
- Fixed reporting tasks being canceled before being picked up by a worker as canceled instead of
  failed.
  :github:`2183`
- Fixed import/export of repositories with sub-content.

  An example would be the sub-repositories in pulp_rpm
  DistributionTrees.
  :github:`2192`
- touch() now uses standard Django instead of raw-sql to update.
  :github:`2229`
- PulpImporter now unpacks into the task-worker's working directory rather than /tmp. Unpacking
  large files into /tmp could cause the operation to fail, or even cause stability issues for
  Pulp instance, due to running /tmp out of space.
  :github:`2247`
- This fix prevents the lost track of a content removed version when deleting a repository version that deletes a content that is added back in the subsequent version, but deleted again in a later version.
  :github:`2267`
- Added transactions around repository version operations to prevent data loss.
  :github:`2268`
- Fixed bug where the content app would stop working after a brief loss of connection to the database.
  :github:`2293`


Plugin API
----------

No significant changes.


3.15.4 (2022-01-28)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed downloader retry logic with partially written files.
  :github:`2078`
- Fixed bug where retries of partially downloaded files failed digest and size validation.
  :github:`2135`
- Fixed the calculation of response range headers in streaming answers from the content app.
  :github:`2147`
- Improved messaging around timeout requests.
  :github:`2169`


Misc
~~~~

- :github:`2094`


Plugin API
----------

No significant changes.


3.15.3 (2021-11-30)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed bug where Artifacts were being downloaded even if they were already saved in Pulp.
  (backported from #9542)
  :redmine:`9584`


Plugin API
----------

No significant changes.


3.15.2 (2021-09-02)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed bug where some Openshift environments could not start workers due to a strange Python runtime
  import issue.
  (backported from #9338)
  :redmine:`9342`


Plugin API
----------

No significant changes.


3.15.1 (2021-08-31)
===================
REST API
--------

Bugfixes
~~~~~~~~

- ``RBACContentGuard`` assign/remove permission endpoints now properly return 201 instead of 200
  (backported from #9314)
  :redmine:`9323`


Plugin API
----------

Bugfixes
~~~~~~~~

- Set the default widget type to ``JSONWidget`` for ``JSONFields`` for Model Resources to fix
  django-import-export bug where ``django.db.models.JSONFields`` weren't properly handled.
  (backported from #9307)
  :redmine:`9324`


3.15.0 (2021-08-26)
===================
REST API
--------

Features
~~~~~~~~

- Added encryption in the database for ``Remote`` fields ``username``, ``password``,
  ``proxy_username``, ``proxy_password``, and ``client_key``.
  :redmine:`8192`
- Added feature to reclaim disk space for a list of repositories.
  :redmine:`8459`
- Added ``method`` field to filesystem exporters to customize how they export files. Users can now
  export files by writing them to the filesystem, using hardlinks, or using symlinks.
  :redmine:`8695`
- Changed orphan cleanup task to be a non-blocking task that can be run at any time. Added a
  ``ORPHAN_PROTECTION_TIME`` setting that can be configured for how long orphan Content and
  Artifacts are kept before becoming candidates for deletion by the orphan cleanup task.
  :redmine:`8824`
- Added a ``/v3/exporters/core/filesystem/`` endpoint for exporting publications or repository
  versions to the filesystem.
  :redmine:`8860`
- Added a periodical cleanup to the pulpcore-worker class to keep the `Worker` table clean.
  :redmine:`8931`
- Added new content guard that uses RBAC policies to protect content
  :redmine:`8940`
- Added authentication to the content app.
  :redmine:`8951`
- A new setting ``ALLOW_SHARED_TASK_RESOURCES`` was temporarily added to allow plugins to use specific
  resources concurrently, during task execution. It defaults to ``False``. It will switch to ``True``
  with 3.16 and will eventually be removed.
  :redmine:`9148`


Bugfixes
~~~~~~~~

- In stages-pipeline and new-version sanity-checks, added full error-info on path-problems.
  :redmine:`8133`
- Improved disk usage during the synchronization.
  :redmine:`8295`
- Fixed an internal server error that was raised when a user provided invalid parameters while
  assigning new permissions to an object.
  :redmine:`8500`
- Fixed a bug, where new tasks were assigned to dead workers.
  :redmine:`8779`
- Fixed bug where content app would not respond to ``Range`` HTTP Header in requests when
  ``remote.policy`` was either ``on_demand`` or ``streamed``. For example this request is used by
  Anaconda clients.
  :redmine:`8865`
- Unpublished content can no longer be accessed from content app if publication based-plugin has
  defined their distributions as publication serving
  :redmine:`8870`
- Fixed a bug that caused a serializer to ignore form data for ``pulp_labels``.
  :redmine:`8954`
- Fixed inability for users to disable RBAC at the settings level by changing the
  ``DEFAULT_PERMISSION_CLASSES`` like any user configuring a DRF project expects to.
  :redmine:`8974`
- Fixed signal handling to properly kill a task when double ctrl-c is used to shut down a worker fast.
  :redmine:`8986`
- Added an attempt to cancel a task if a worker needed to abort it on graceful shutdown.
  :redmine:`8987`
- Fixed a bug where on-demand downloads would fill up ``/var/run/`` by not deleting downloaded files.
  :redmine:`9000`
- Fixed a regression preventing syncs from file:// urls.
  :redmine:`9003`
- Removed ambiguity from the OpenAPI schema for Exports. The exported_resources are now a list of URI strings.
  :redmine:`9008`
- Use proxy auth from Remote config to download content from a remote repository.
  :redmine:`9024`
- Fixed the behavior of setting "repository" on a distribution for publication-based plugins.
  :redmine:`9039`
- Set Redis connection information in status to null unless it's used. Redis is
  needed for RQ tasking or content caching.
  :redmine:`9070`
- Fixed server error when accessing invalid files from content app base directory
  :redmine:`9074`
- Fixed improper validation of remotes' URLs.
  :redmine:`9080`
- Artifacts are now being properly updated for Content after switching from 'on_demand' to 'immediate'.
  :redmine:`9101`
- Made all database queries run serially using a single connection to the database.
  :redmine:`9129`
- Move files to artifact storage only when they originate from WORKING_DIRECTORY.
  Copy files from all other sources.
  :redmine:`9146`
- Content app now properly sets Content-Type header for artifacts being served from S3
  :redmine:`9216`
- Fixed repository sync performance regression introduced in pulpcore 3.14.
  :redmine:`9243`
- Stop using insecure hash function blake2s for calculating 64 bit lock identifier from uuid.
  :redmine:`9249`
- Fixed another occurence of the HTTP 500 error and `connection already closed` in the logs while accessing content.
  :redmine:`9275`


Removals
~~~~~~~~

- Dropped support for Python 3.6 and 3.7. Pulp now supports Python 3.8+.
  :redmine:`8855`
- Renamed the ``retained_versions`` field on repositories to ``retain_repo_versions``.
  :redmine:`9030`


Deprecations
~~~~~~~~~~~~

- The traditional tasking system (formerly the default in ``pulpcore<=3.13``) is deprecated and
  will be removed in ``pulpcore==3.16``. If you are using the ``USE_NEW_WORKER_TYPE=False`` that
  will no longer give you the traditional tasking system starting with ``pulpcore==3.16``.
  :redmine:`9159`


Misc
~~~~

- :redmine:`5582`, :redmine:`8996`, :redmine:`9010`, :redmine:`9056`, :redmine:`9112`, :redmine:`9120`, :redmine:`9171`, :redmine:`9174`


Plugin API
----------

Features
~~~~~~~~

- Content model has a new boolean class constant ``PROTECTED_FROM_RECLAIM`` for plugins to enable the
  reclaim disk space feature provided by core.
  :redmine:`8459`
- Added endpoints for managing Alternate Content Sources.
  :redmine:`8607`
- Orphan cleanup task has a new optional parameter ``orphan_protection_time`` that decides for how
  long Pulp will hold orphan Content and Artifacts before they become candidates for deletion for this
  particular orphan cleanup task.
  :redmine:`8824`
- Distribution model has a new boolean class variable ``SERVE_FROM_PUBLICATION`` for plugins to declare
  whether their distributions serve from publications or directly from repository versions
  :redmine:`8870`
- The settings file switched ``DEFAULT_PERMISSION_CLASSES`` to use ``AccessPolicyFromDB`` instead of
  ``IsAdminUser`` with a fallback to a behavior of ``IsAdminUser``. With this feature plugin writers
  no longer need to declare ``permission_classes`` on their Views or Viewsets to use
  ``AccessPolicyFromDB``.
  :redmine:`8974`
- Upgraded django from 2.2 to 3.2.
  :redmine:`9018`
- `pulpcore.plugin.models.ProgressReport` now has async interfaces: asave(), aincrease_by(),
  aincrement(), __aenter__(), _aexit__(). Plugins should switch to the async interfaces in their
  Stages.
  `pulpcore.plugin.sync.sync_to_async_iterator` is a utility method to synchronize the database
  queries generated when a QuerySet is iterated.
  :redmine:`9129`
- Added ``shared_resources`` to the ``dispatch`` call, so tasks can run concurrently if they need overlapping resources for read only.
  :redmine:`9148`
- Added ``touch`` to Artifact and Content query sets for bulk operation.
  :redmine:`9234`
- Added `ContentManager` to the plugin API - all subclasses of `Content` that add their own custom manager should have the manager subclass `ContentManager`.
  :redmine:`9269`


Bugfixes
~~~~~~~~

- Added kwarg to RemoteArtifactSaver init to allow enabling handling of rare error edge-case.

  `fix_mismatched_remote_artifacts=True` enables workaround for a failure-scenario that
  (so far) is only encountered by pulp_rpm. Current behavior is the default.
  :redmine:`8133`


Removals
~~~~~~~~

- Removed the ``pulpcore.plugin.viewsets.NewDistributionFilter``. Instead use
  ``pulpcore.plugin.viewsets.DistributionFilter``.
  :redmine:`8479`
- Removed ``FilesystemExporterSerializer`` and ``PublicationExportSerializer`` from the plugin api.
  Filesystem exports are now handled by pulpcore.
  :redmine:`8860`
- The ``pulpcore.plugin.download.http_giveup`` method has been removed from the plugin API. Plugins
  used to have to use this to wrap the ``_run`` method defined on subclasses of ``HttpDownloader``,
  but starting with pulpcore 3.14 the backoff is implemented directly in the ``HttpDownloader.run()``
  method which subclasses do not override. Due to ``pulpcore`` implementing it, it is no longer needed
  or available for plugins to use.
  :redmine:`8913`


Deprecations
~~~~~~~~~~~~

- ContentSaver._pre_save() and ContentSaver._post_save() hooks are no longer coroutines. They should
  be implemented as synchronous functions.
  :redmine:`9129`
- Deprecate the compatibility layer for access policies. As of pulpcore 3.16, all plugins should
  properly use the "condition" and "condition_expression" fields in the access policy statements.
  :redmine:`9160`
- Deprecate the ``resources`` argument of ``dispatch`` in favor of ``exclusive_resources`` and ``shared_resources``.
  :redmine:`9257`


Misc
~~~~

- :redmine:`8606`, :redmine:`9160`


3.14.18 (2022-07-14)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Started showing errors when users try to export remote artifacts.
  :github:`2817`
- Restore multiple-retry logic for PulpImport.
  :github:`2854`
- Configured aiohttp to avoid rewriting redirect URLs, as some web servers (e.g. Amazon CloudFront) can be tempermental about the encoding of the URL.
  :github:`2964`


Plugin API
----------

No significant changes.


3.14.17 (2022-05-09)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Loosened the version-restrictions on PulpImport to only require X.Y matching.
  :github:`2269`
- Taught PulpImport to stream imports rather than reading files into memory in one chunk.

  This largely alleviates the memory-pressure that results from importing multiple
  large repositories in parallel.
  :github:`2307`
- Ensure downloader resets file on retry.
  :github:`2576`
- Taught PulpImport to retry more than once in the event of creation-collisions.

  This fixes a rare import-failure during high-concurrency, high-content-overlap imports.
  :github:`2589`


Plugin API
----------

No significant changes.


3.14.16 (2022-04-12)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed two instances of Pulp not writing to the task worker's temporary directory.
  :github:`2061`
- Fixed a (rare) deadlock around bulk_update() during syncs with overlapping content.
  :github:`2430`
- Fixed a bug where notifications to workers may go unnoticed. This may lead to idle workers while
  there are tasks waiting.
  :github:`2506`


Plugin API
----------

No significant changes.


3.14.15 (2022-03-25)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fix delete repository version causing "duplicate key value violates unique constraint" error.
  :github:`2047`
- Reduced memory usage during tasks like sync by holding fewer objects in-memory unnecessarily.
  :github:`2069`
- This fix prevents the lost track of a content removed version when deleting a repository version that deletes a content that is added back in the subsequent version, but deleted again in a later version.
  :github:`2267`
- Fixes duplicate key error ``Key (content_artifact_id, remote_id)`` when creating ``RemoteArtifacts``
  during syncs in pulp_container and possibly other plugins.
  :github:`2381`
- Declared proper dependency on user model in migration 0040.
  :github:`2403`
- Fixed a rare deadlock when sync'ing overlapping content in high-concurrency envs.
  :github:`2420`


Plugin API
----------

Bugfixes
~~~~~~~~

- Adjusted the default size of the queues between pipelines to be 1 instead of 1000. The batchers in
  the stage will still accumulate up to 500 (by default) items so batching is still in-effect there
  where it matters.
  :github:`2069`


3.14.14 (2022-03-10)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed migration 0064_add_new_style_task_columns to purge extraneous ReservedResource and
  TaskReservedResource entries, which could block sync and publish tasks post-upgrade.

  Also taught the migration to bulk-update the Task changes. In large installations, this
  should have a positive impact on the time it takes to apply the migration.
  :github:`2101`


Plugin API
----------

No significant changes.


3.14.13 (2022-03-08)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Taught PulpImport to retry in the event of a concurrency-collision on ContentArtifact.
  :github:`2102`
- Fixed import/export of repositories with sub-content.

  An example would be the sub-repositories in pulp_rpm
  DistributionTrees.
  :github:`2192`
- touch() now uses standard Django instead of raw-sql to update.
  :github:`2229`
- PulpImporter now unpacks into the task-worker's working directory rather than /tmp. Unpacking
  large files into /tmp could cause the operation to fail, or even cause stability issues for
  Pulp instance, due to running /tmp out of space.
  :github:`2247`


3.14.12 (2022-02-11)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed potential deadlock-window in touch() path.
  :github:`2157`
- Fixed reporting tasks being canceled before being picked up by a worker as canceled instead of
  failed.
  :github:`2183`


Plugin API
----------

No significant changes.


3.14.11 (2022-01-27)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fix import and export OOM error.
  :github:`2072`
- Fixed downloader retry logic with partially written files.
  :github:`2078`
- Fix content summary showing incorrect count after previous version deletion.
  :github:`2084`
- Fixed issue with listing repository versions after deleting previous versions.
  :github:`2085`
- Fixed file descriptior leak during upload.
  :github:`2087`
- Added proper logging around certain ways a task could fail.
  :github:`2093`
- Make checksum mismatches a retryable error.
  :github:`2094`
- Fixed an edge case where the first (streamed) response from an repo synced as "on_demand" could be incorrect.
  :github:`2119`
- Fixed bug where retries of partially downloaded files failed digest and size validation.
  :github:`2135`
- Fixed a bug in pulpcore-worker, where wakeup and cancel signals could be lost due to a race
  condition.
  :github:`2144`
- Fixed the calculation of response range headers in streaming answers from the content app.
  :github:`2147`


Plugin API
----------

No significant changes.


3.14.10 (2022-01-07)
====================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed PulpImport to correctly save relative to MEDIA_ROOT.
  (backported from #9660)
  :redmine:`9662`


Plugin API
----------

No significant changes.


3.14.9 (2021-11-05)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a bug where the `/pulp/content/` page would return a 500 error after the database connection
  was closed due to a network problem or a database restart.
  :redmine:`9515`
- Fixed bug where chunked uploads were being assembled in /tmp.
  :redmine:`9556`


Plugin API
----------

No significant changes.


3.14.8 (2021-10-06)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Improved messaging around timeout requests. (Backported from :redmine:`9301`).
  :redmine:`9491`


Plugin API
----------

No significant changes.


3.14.7 (2021-09-29)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Added a periodical cleanup to the pulpcore-worker class to keep the `Worker` table clean.
  (backported from #8931)
  :redmine:`9462`
- Ordered several ContentStages paths to fix deadlocks in high-concurrency scenarios.
  (backported from #8750)
  :redmine:`9379`
- Fixed an issue where on_demand content might not be downloaded properly if the remote URL was changed (even if re-synced).
  (backported from #9395)
  :redmine:`9400`
- Fixed the repository modify endpoint performance problems.
  (backported from #9266)
  :redmine:`9401`
- Taught a remote-artifact error path to not assume 'filename' was valid for all content.
  (backported from #9427)
  :redmine:`9440`
- Taught several more codepaths to order-before-update to avoid deadlocks.
  (backported from #9441)
  :redmine:`9445`
- Changed the pulpcore-worker to mark abandoned tasks as "failed" instead of "canceled".
  (backported from #9247)
  :redmine:`9453`


Plugin API
----------

No significant changes.


3.14.6 (2021-09-02)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Stop using insecure hash function blake2s for calculating 64 bit lock identifier from uuid.
  (backported from #9249)
  :redmine:`9288`
- Fixed a bug where ``pulpcore-content`` decompressed data while incorrectly advertising to clients
  it was still compressed via the ``Content-Encoding: gzip`` header.
  (backported from #9213)
  :redmine:`9325`
- Fixed bug where some Openshift environments could not start workers due to a strange Python runtime
  import issue.
  (backported from #9338)
  :redmine:`9339`


Plugin API
----------

No significant changes.


3.14.5 (2021-08-24)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Content app now properly sets Content-Type header for artifacts being served from S3
  (backported from #9216)
  :redmine:`9244`
- Artifacts are now being properly updated for Content after switching from 'on_demand' to 'immediate'.
  (backported from #9101)
  :redmine:`9261`
- Fixed repository sync performance regression introduced in pulpcore 3.14.
  (backported from #9243)
  :redmine:`9264`
- Fixed another occurence of the HTTP 500 error and `connection already closed` in the logs while accessing content.
  (backported from #9275)
  :redmine:`9282`


Misc
~~~~

- :redmine:`9265`


Plugin API
----------

Misc
~~~~

- :redmine:`9268`, :redmine:`9273`


3.14.4 (2021-08-10)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Unpublished content can no longer be accessed from content app if publication based-plugin has
  defined their distributions as publication serving
  (backported from #8870)
  :redmine:`9126`
- In stages-pipeline and new-version sanity-checks, added full error-info on path-problems.
  (backported from #8133)
  :redmine:`9130`
- Move files to artifact storage only when they originate from WORKING_DIRECTORY.
  Copy files from all other sources.
  (backported from #9146)
  :redmine:`9202`


Misc
~~~~

- :redmine:`9179`


Plugin API
----------

Features
~~~~~~~~

- Distribution model has a new boolean class variable ``SERVE_FROM_PUBLICATION`` for plugins to declare
  whether their distributions serve from publications or directly from repository versions
  (backported from #8870)
  :redmine:`9126`


Bugfixes
~~~~~~~~

- Added kwarg to RemoteArtifactSaver init to allow enabling handling of rare error edge-case.

  `fix_mismatched_remote_artifacts=True` enables workaround for a failure-scenario that
  (so far) is only encountered by pulp_rpm. Current behavior is the default.
  (backported from #8133)
  :redmine:`9130`


3.14.3 (2021-07-23)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed improper validation of remotes' URLs.
  (backported from #9080)
  :redmine:`9083`
- Set Redis connection information in status to null unless it's used. Redis is
  needed for RQ tasking or content caching.
  (backported from #9070)
  :redmine:`9085`
- Fixed signal handling to properly kill a task when double ctrl-c is used to shut down a worker fast.
  (backported from #8986)
  :redmine:`9086`
- Improved disk usage during the synchronization.
  (backported from #8295)
  :redmine:`9103`
- Fixed a bug where on-demand downloads would fill up ``/var/run/`` by not deleting downloaded files.
  (backported from #9000)
  :redmine:`9110`
- Fixed a bug, where new tasks were assigned to dead workers.
  (backported from #8779)
  :redmine:`9116`


Plugin API
----------

No significant changes.


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
  :redmine:`9057`
- Fixed a bug that caused a serializer to ignore form data for ``pulp_labels``.
  (backported from #8954)
  :redmine:`9058`
- Fixed the behavior of setting "repository" on a distribution for publication-based plugins.
  (backported from #9039)
  :redmine:`9059`
- Use proxy auth from Remote config to download content from a remote repository.
  (backported from #9024)
  :redmine:`9068`
- Fixed server error when accessing invalid files from content app base directory
  (backported from #9074)
  :redmine:`9077`


Misc
~~~~

- :redmine:`9063`


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
  :redmine:`9015`
- Removed ambiguity from the OpenAPI schema for Exports. The exported_resources are now a list of URI strings.
  (backported from #9008)
  :redmine:`9025`


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
  :redmine:`8501`
- Added new endpoint ``/pulp/api/v3/orphans/cleanup/``. When called with ``POST`` and no parameters
  it is equivalent to calling ``DELETE /pulp/api/v3/orphans/``. Additionally the optional parameter
  ``content_hrefs`` can be specified and must contain a list of content hrefs. When ``content_hrefs``
  is specified, only those content units will be considered to be removed by orphan cleanup.
  :redmine:`8658`
- Content app responses are now smartly cached in Redis.
  :redmine:`8805`
- Downloads from remote sources will now be retried on more kinds of errors, such as HTTP 500 or socket errors.
  :redmine:`8881`
- Add a correlation id filter to the task list endpoint.
  :redmine:`8891`
- Where before ``download_concurrency`` would previously be set to a default value upon creation, it will now be set NULL (but a default value will still be used).
  :redmine:`8897`
- Added graceful shutdown to pulpcore workers.
  :redmine:`8930`
- Activate the new task worker type by default.

  .. warning::

     If you intend to stick with the old tasking system, you should configure the
     ``USE_NEW_WORKER_TYPE`` setting to false before upgrade

  :redmine:`8948`


Bugfixes
~~~~~~~~

- Fixed race condition where a task could clean up reserved resources shared with another task.
  :redmine:`8637`
- Altered redirect URL escaping, preventing invalidation of signed URLs for artifacts using cloud storage.
  :redmine:`8670`
- Add an update row lock on in task dispatching for ``ReservedResource`` to prevent a race where an
  object was deleted that was supposed to be reused. This prevents a condition where tasks ended up in
  waiting state forever.
  :redmine:`8708`
- Retry downloads on ``ClientConnectorSSLError``, which appears to be spuriously returned by some CDNs.
  :redmine:`8867`
- Fixed OpenAPI schema tag generation for resources that are nested more than 2 levels.

  This change is most evident in client libraries generated from the OpenAPI schema.

  Prior to this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` was named `ExportersCoreExportsApi`.

  After this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` is named `ExportersPulpExportsApi`.
  :redmine:`8868`
- Fixed request schema for ``/pulp/api/v3/repair/``, which did identify any arguments. This also fixes
  the bindings.
  :redmine:`8869`
- Update default access policies in the database if they were unmodified by the administrator.
  :redmine:`8883`
- Pinning to psycopg2 < 2.9 as psycopg 2.9 doesn't work with django 2.2. More info at
  https://github.com/django/django/commit/837ffcfa681d0f65f444d881ee3d69aec23770be.
  :redmine:`8926`
- Fixed bug where artifacts and content were not always saved in Pulp with each
  on_demand request serviced by content app.
  :redmine:`8980`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Fixed a number of link-problems in the installation/ section of docs.
  :redmine:`6837`
- Added a troubleshooting section to the docs explaining how to find stuck tasks.
  :redmine:`8774`
- Moved existing basic auth docs to a new top-level section named Authentication.
  :redmine:`8800`
- Moved ``Webserver Authentication`` docs under the top-level ``Authentication`` section.
  :redmine:`8801`
- Provide instructions to use Keycloak authenication using Python Social Aauth
  :redmine:`8803`
- Updated the docs.pulpproject.org to provide some immediate direction for better user orientation.
  :redmine:`8946`
- Separated hardware and Filesystem information from the Architecture section and added them to the Installation section.
  :redmine:`8947`
- Added sub-headings and simplified language of Pulp concept section.
  :redmine:`8949`


Deprecations
~~~~~~~~~~~~

- Deprecated the ``DELETE /pulp/api/v3/orphans/`` call. Instead use the
  ``POST /pulp/api/v3/orphans/cleanup/`` call.
  :redmine:`8876`


Misc
~~~~

- :redmine:`8821`, :redmine:`8827`, :redmine:`8975`


Plugin API
----------

Features
~~~~~~~~

- Added the ``pulpcore.plugin.viewsets.DistributionFilter``. This should be used instead of
  ``pulpcore.plugin.viewsets.NewDistributionFilter``.
  :redmine:`8480`
- Added ``user_hidden`` field to ``Repository`` to hide repositories from users.
  :redmine:`8487`
- Added a ``timestamp_of_interest`` field to Content and Artifacts. This field can be updated by
  calling a new method ``touch()`` on Artifacts and Content. Plugin writers should call this method
  whenever they deal with Content or Artifacts. For example, this includes places where Content is
  uploaded or added to Repository Versions. This will prevent Content and Artifacts from being cleaned
  up when orphan cleanup becomes a non-blocking task in pulpcore 3.15.
  :redmine:`8823`
- Exposed ``AsyncUpdateMixin`` through ``pulpcore.plugin.viewsets``.
  :redmine:`8844`
- Added a field ``DEFAULT_MAX_RETRIES`` to the ``Remote`` base class - plugin writers can override the default number of retries attempted when file downloads failed for each type of remote. The default value is 3.
  :redmine:`8881`
- Added a field ``DEFAULT_DOWNLOAD_CONCURRENCY`` to the Remote base class - plugin writers can override the number of concurrent downloads for each type of remote. The default value is 10.
  :redmine:`8897`


Bugfixes
~~~~~~~~

- Fixed OpenAPI schema tag generation for resources that are nested more than 2 levels.

  This change is most evident in client libraries generated from the OpenAPI schema.

  Prior to this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` was named `ExportersCoreExportsApi`.

  After this change, the API client for a resource located at
  `/api/v3/pulp/exporters/core/pulp/<uuid>/exports/` is named `ExportersPulpExportsApi`.
  :redmine:`8868`


Removals
~~~~~~~~

- The usage of non-JSON serializable types of ``args`` and ``kwargs`` to tasks is no longer supported.
  ``uuid.UUID`` objects however will silently be converted to ``str``.
  :redmine:`8501`
- Removed the ``versions_containing_content`` method from the
  `pulpcore.plugin.models.RepositoryVersion`` object. Instead use
  ``RepositoryVersion.objects.with_content()``.
  :redmine:`8729`
- Removed `pulpcore.plugin.stages.ContentUnassociation` from the plugin API.
  :redmine:`8827`


Deprecations
~~~~~~~~~~~~

- The ``pulpcore.plugin.viewsets.NewDistributionFilter`` is deprecated and will be removed from a
  future release. Instead use ``pulpcore.plugin.viewsets.DistributionFilter``.
  :redmine:`8480`
- Deprecate the use of the `reserved_resources_record__resource` in favor of `reserved_resources_record__contains`.
  Tentative removal release is pulpcore==3.15.
  :redmine:`8501`
- Plugin writers who create custom downloaders by subclassing ``HttpDownloader`` no longer need to wrap the ``_run()`` method with a ``backoff`` decorator. Consequntly the ``http_giveup`` handler the sake of the ``backoff`` decorator is no longer needed and has been deprecated. It is likely to be removed in pulpcore 3.15.
  :redmine:`8881`


3.13.0 (2021-05-25)
===================
REST API
--------

Features
~~~~~~~~

- Added two views to identify content which belongs to repository_version or publication.
  :redmine:`4832`
- Added repository field to repository version endpoints.
  :redmine:`6068`
- Added ability for users to limit how many repo versions Pulp retains by setting
  ``retained_versions`` on repository.
  :redmine:`8368`
- Added the ``add-signing-service`` management command.
  Notice that it is still in tech-preview and can change without further notice.
  :redmine:`8609`
- Added a ``pulpcore-worker`` entrypoint to simplify and unify the worker command.
  :redmine:`8721`
- Content app auto-distributes latest publication if distribution's ``repository`` field is set
  :redmine:`8760`


Bugfixes
~~~~~~~~

- Fixed cleanup of UploadChunks when their corresponding Upload is deleted.
  :redmine:`7316`
- Fixed an issue that caused the request's context to be ignored in the serializers.
  :redmine:`8396`
- Fixed missing ``REDIS_SSL`` parameter in RQ config.
  :redmine:`8525`
- Fixed bug where using forms submissions to create resources (e.g. ``Remotes``) raised exception
  about the format of ``pulp_labels``.
  :redmine:`8541`
- Fixed bug where publications sometimes fail with the error '[Errno 39] Directory not empty'.
  :redmine:`8595`
- Handled a tasking race condition where cleaning up resource reservations sometimes raised an IntegrityError.
  :redmine:`8603`
- Fixed on-demand sync/migration of repositories that don't have sha256 checksums.
  :redmine:`8625`
- Taught pulp-export to validate chunk-size to be <= 1TB.
  :redmine:`8628`
- Addressed a race-condition in PulpImport that could fail with unique-constraint violations.
  :redmine:`8633`
- Content app now properly lists all distributions present
  :redmine:`8636`
- Fixed ability to specify custom headers on a Remote.
  :redmine:`8689`
- Fixed compatibility with Django 2.2 LTS. Pulp now requires Django~=2.2.23
  :redmine:`8691`
- Skip allowed content checks on collectstatic
  :redmine:`8711`
- Fixed a bug in the retained versions code where content wasn't being properly moved to newer repo
  versions when old versions were cleaned up.
  :redmine:`8793`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added docs on how to list the effective settings using ``dynaconf list``.
  :redmine:`6235`
- Added anti-instructions, that users should never run `pulpcore-manager makemigrations``, but file a bug instead.
  :redmine:`6703`
- Clarified repositories are typed in concepts page
  :redmine:`6990`
- Added UTF-8 character set encoding as a requirement for PostgreSQL
  :redmine:`7019`
- Fixed typo s/comtrol/control
  :redmine:`7715`
- Removed the PUP references from the docs.
  :redmine:`7747`
- Updated plugin writers' guide to not use settings directly in the model fields.
  :redmine:`7776`
- Make the reference to the Pulp installer documentation more explicit.
  :redmine:`8477`
- Removed example Ansible installer playbook from the pulpcore docs so that Pulp users would have a single source of truth in the pulp-installer docs.
  :redmine:`8550`
- Added security disclosures ref to homepage
  :redmine:`8584`
- Add sequential steps for storage docs
  :redmine:`8597`
- Updated signing service workflow. Removed old deprecation warning.
  :redmine:`8609`
- Add an example of how to specify an array value and a dict key in the auth methods section
  :redmine:`8668`
- Fixed docs build errors reported by autodoc.
  :redmine:`8784`


Misc
~~~~

- :redmine:`8524`, :redmine:`8656`, :redmine:`8761`


Plugin API
----------

Features
~~~~~~~~

- Undeprecated the use of ``uuid.UUID`` in task arguments. With this, primary keys do not need to be explicitely cast to ``str``.
  :redmine:`8723`


Bugfixes
~~~~~~~~

- Added RepositoryVersionRelatedField to the plugin API.
  :redmine:`8578`
- Fixed auto-distribute w/ retained_versions tests
  :redmine:`8792`


Removals
~~~~~~~~

- Removed deprecated ``pulpcore.plugin.tasking.WorkingDirectory``.
  :redmine:`8354`
- Removed ``BaseDistribution``, ``PublicationDistribution``, and ``RepositoryVersionDistribution``
  models. Removed ``BaseDistributionSerializer``, ``PublicationDistributionSerializer``, and
  ``RepositoryVersionDistributionSerializer`` serializers. Removed ``BaseDistributionViewSet`` and
  ``DistributionFilter``.
  :redmine:`8386`
- Removed ``pulpcore.plugin.tasking.enqueue_with_reservation``.
  :redmine:`8497`


Deprecations
~~~~~~~~~~~~

- RepositoryVersion method "versions_containing_content" is deprecated now.
  :redmine:`4832`
- The usage of the `pulpcore.plugin.stages.ContentUnassociation` stage has been deprecated. A future update will remove it from the plugin API.
  :redmine:`8635`


3.12.2 (2021-04-29)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Backported a fix for on-demand sync/migration of repositories that don't have sha256 checksums.
  :redmine:`8652`


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
  :redmine:`8580`


3.12.0 (2021-04-08)
===================
REST API
--------

Features
~~~~~~~~

- Add support for automatic publishing and distributing.
  :redmine:`7626`
- Add a warning at startup time if there are remote artifacts with checksums but no allowed checksums.
  :redmine:`7985`
- Added support in content app for properly handling unknown or forbidden digest errors.
  :redmine:`7989`
- Added sync check that raises error when only forbidden checksums are found for on-demand content.
  :redmine:`8423`
- Added ability for users to delete repo version 0 as long as they still have at least one repo
  version for their repo.
  :redmine:`8454`


Bugfixes
~~~~~~~~

- Added asynchronous tasking to the Update and Delete endpoints of PulpExporter to provide proper locking on resources.
  :redmine:`7438`
- Fixed a scenario where canceled tasks could be marked failed.
  :redmine:`7980`
- Taught ``PulpImport`` correct way to find and import ``RepositoryVersions``. Previous
  implementation only worked for ``RepositoryVersions`` that were the 'current' version
  of the exported ``Repository``.
  :redmine:`8116`
- Fixed a race condition that sometimes surfaced during handling of reserved resources.
  :redmine:`8352`
- Made digest and size sync erros more helpful by logging url of the requested files.
  :redmine:`8357`
- Fixed artifact-stage to handle an edge-case when multiple multi-artifact content, from different remotes, is in a single batch.
  :redmine:`8377`
- Fixed Azure artifacts download.
  :redmine:`8427`
- Fixed bug during sync where a unique constraint violation for ``Content`` would raise an "X matching
  query does not exist" error.
  :redmine:`8430`
- Fix artifact checksum check to not check on-demand content.
  :redmine:`8445`
- Fixed a bug where the existence of PublishedMetadata caused ``LookupError`` when querying ``/pulp/api/v3/content/``
  :redmine:`8447`
- Distributions are now viewable again at the base url of the content app
  :redmine:`8475`
- Fixed a path in artifact_stages that could lead to sync-failures in pulp_container.
  :redmine:`8489`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Update docs with guide how to change 'ALLOWED_CONTENT_CHECKSUMS' setting using 'pulpcore-manager handle-artifact-checksums --report' if needed.
  :redmine:`8325`


Removals
~~~~~~~~

- The Update and Delete endpoints of Exporters changed to now return 202 with tasks.
  :redmine:`7438`
- Deprecation warnings are now being logged by default if the log level includes WARNING. This can be
  disabled by adjusting the log level of ``pulpcore.deprecation``. See the deprecation docs for more
  information.
  :redmine:`8499`


Misc
~~~~

- :redmine:`8450`


Plugin API
----------

Features
~~~~~~~~

- Added a new callback method to ``Repository`` named ``on_new_version()``, which runs when a new repository version has been created. This can be used for e.g. automatically publishing or distributing a new repository version after it has been created.
  :redmine:`7626`
- Added url as optional argument to ``DigestValidationError`` and ``SizeValidationError`` exceptions to log urls in the exception message.
  :redmine:`8357`
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
  :redmine:`8384`
- Added checksum type enforcement to ``pulpcore.plugin.download.BaseDownloader``.
  :redmine:`8435`
- Adds the ``pulpcore.plugin.tasking.dispatch`` interface which replaces the
  ``pulpcore.plugin.tasking.enqueue_with_reservation`` interface. It is the same except:
  * It returns a ``pulpcore.plugin.models.Task`` instead of an RQ object
  * It does not support the ``options`` keyword argument

  Additionally the ``pulpcore.plugin.viewsets.OperationPostponedResponse`` was updated to support both
  the ``dispatch`` and ``enqueue_with_reservation`` interfaces.
  :redmine:`8496`


Bugfixes
~~~~~~~~

- Allow plugins to unset the ``queryset_filtering_required_permission`` attribute in ``NamedModelViewSet``.
  :redmine:`8438`


Removals
~~~~~~~~

- Removed checksum type filtering from ``pulpcore.plugin.models.Remote.get_downloader`` and ``pulpcore.plugin.stages.DeclarativeArtifact.download``.
  :redmine:`8435`


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

  :redmine:`8385`
- Deprecated the ``pulpcore.plugin.tasking.enqueue_with_reservation``. Instead use the
  ``pulpcore.plugin.tasking.dispatch`` interface.
  :redmine:`8496`
- The usage of non-JSON serializable types of ``args`` and ``kwargs`` to tasks is deprecated. Future
  releases of pulpcore may discontinue accepting complex argument types. Note, UUID objects are not
  JSON serializable. A deprecated warning is logged if a non-JSON serializable is used.
  :redmine:`8505`


3.11.2 (2021-05-25)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Skip allowed content checks on collectstatic
  (backported from #8711)
  :redmine:`8712`
- Fixed cleanup of UploadChunks when their corresponding Upload is deleted.
  (backported from #7316)
  :redmine:`8757`
- Fixed compatibility with Django 2.2 LTS. Pulp now requires Django~=2.2.23
  (backported from #8691)
  :redmine:`8758`
- Pinned click~=7.1.2 to ensure RQ is compatible with it.
  :redmine:`8767`


Plugin API
----------

No significant changes.


3.11.1 (2021-04-29)
===================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a race condition that sometimes surfaced during handling of reserved resources.
  :redmine:`8632`
- Handled a tasking race condition where cleaning up resource reservations sometimes raised an IntegrityError.
  :redmine:`8648`


Plugin API
----------

Bugfixes
~~~~~~~~

- Allow plugins to unset the ``queryset_filtering_required_permission`` attribute in ``NamedModelViewSet``.
  :redmine:`8444`


3.11.0 (2021-03-15)
===================
REST API
--------

Features
~~~~~~~~

- Raise error when syncing content with a checksum not included in ``ALLOWED_CONTENT_CHECKSUMS``.
  :redmine:`7854`
- User can evaluate how many content units are affected with checksum type change with 'pulpcore-manager handle-artifact-checksums --report'.
  :redmine:`7986`
- The fields ``proxy_username`` and ``proxy_password`` have been added to remotes.
  Credentials can no longer be specified as part of the ``proxy_url``.
  A data migration will move the proxy auth information on existing remotes to the new fields.
  :redmine:`8167`
- Added the ``WORKER_TTL`` setting, that specifies the interval a worker is considered missing after its last heartbeat.
  :redmine:`8291`
- Due to the removal of ``md5`` and ``sha1`` from the ``ALLOWED_CONTENT_CHECKSUMS`` setting, every
  system that had any Artifacts synced in in prior to 3.11 will have to run the ``pulpcore-manager
  handle-content-checksums`` command. A data migration is provided with 3.11 that will run this
  automatically as part of the ``pulpcore-manager migrate`` command all upgrades must run anyway.
  :redmine:`8322`


Bugfixes
~~~~~~~~

- Fixed a bug experienced by the migration plugin where all content objects are assumed to have a
  remote associated with them.
  :redmine:`7876`
- Restored inadvertently-changed content-guards API to its correct endpoint.

  In the process of adding generic list-endpoints, the /pulp/api/v3/contentguards
  API was inadvertently rehomed to /pulp/api/v3/content_guards. This change restores
  it to its published value.
  :redmine:`8283`
- Added headers field to the list of fields in the ``RemoteSerializer`` base class and marked it optional to make it accessible via the REST api.
  :redmine:`8330`
- Fixed AccessPolicy AttributeError.
  :redmine:`8395`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Removed correlation id feature from tech preview.
  :redmine:`7927`
- Removed 'tech preview' label from ``handle-artifact-checksums`` command.

  ``handle-artifact-checksums`` is now a fully-supported part of Pulp3.
  :redmine:`7928`
- Added a warning banner to the ``ALLOWED_CONTENT_CHECKSUMS`` setting section indicating the setting
  is not fully enforcing in ``pulpcore`` code and various plugins.
  :redmine:`8342`


Removals
~~~~~~~~

- The ``component`` field of the ``versions`` section of the status API ```/pulp/api/v3/status/`` now
  lists the Django app name, not the Python package name. Similarly the OpenAPI schema at
  ``/pulp/api/v3`` does also.
  :redmine:`8198`
- Removed sensitive fields ``username``, ``password``, and ``client_key`` from Remote responses. These
  fields can still be set and updated but will no longer be readable.
  :redmine:`8202`
- Adjusted the ``ALLOWED_CONTENT_CHECKSUMS`` setting to remove ``md5`` and ``sha1`` since they are
  insecure. Now, by default, the ``ALLOWED_CONTENT_CHECKSUMS`` contain ``sha224``, ``sha256``,
  ``sha384``, and ``sha512``.
  :redmine:`8246`


Misc
~~~~

- :redmine:`7797`, :redmine:`7984`, :redmine:`8315`


Plugin API
----------

Features
~~~~~~~~

- Allow developers to use more than one WorkingDirectory() within a task, including nested calls. Tasks will also now use a temporary working directory by default.
  :redmine:`7815`
- Added the ``pulpcore.app.pulp_hashlib`` module which provides the ``new`` function and ensures only
  allowed hashers listed in ``ALLOWED_CONTENT_CHECKSUMS`` can be instantiated. Plugin writers should
  use this instead of ``hashlib.new`` to generate checksum hashers.
  :redmine:`7984`
- Add a ``get_content`` method to ``pulpcore.plugin.models.RepositoryVersion`` that accepts a
  queryset and returns a list of content in that repository using the given queryset.
  This allows for specific content type to be returned by executing
  ``repo_version.get_content(content_qs=MyContentType.objects)``.
  :redmine:`8375`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added docs identifying plugin writers to use the ``pulpcore.app.pulp_hashlib`` module which provides
  the ``new`` function and ensures only allowed hashers can be instantiated. This should be used in
  place of ``hashlib.new``.
  :redmine:`7984`
- The use of ``tempdir.TemporaryDirectory`` in tasks has been documented.
  :redmine:`8231`


Removals
~~~~~~~~

- Adjusted the ``ALLOWED_CONTENT_CHECKSUMS`` setting to remove ``md5`` and ``sha1`` since they are
  insecure. Now, by default, the ``ALLOWED_CONTENT_CHECKSUMS`` contain ``sha224``, ``sha256``,
  ``sha384``, and ``sha512``.
  :redmine:`8246`
- Removed unused `get_plugin_storage_path` method.
  :redmine:`8343`
- It is not longer possible to address AccessPolicy via the viewset's classname. Viewset's urlpattern should be used instead.
  :redmine:`8397`
- Removed deprecated `key` field returned by the signing service.
  Plugin writers must now refer directly to the `public_key` field on the signing service object.
  :redmine:`8398`


Deprecations
~~~~~~~~~~~~

- ``pulpcore.plugin.tasking.WorkingDirectory`` has been deprecated.
  :redmine:`8231`


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
  :redmine:`7178`
- Added general endpoints to list ``Content``, ``ContentGuards``, and ``Repositories``.
  :redmine:`7204`
- Added /importers/core/pulp/import-check/ to validate import-parameters.
  :redmine:`7549`
- Added a new field called public_key to SigningService. This field preserves the value of the public
  key. In addition to that, the field fingerprint was introduced as well. This field identifies the
  public key.
  :redmine:`7700`
- Added possibility to filter users and groups by various fields.
  :redmine:`7975`
- Added pulp_labels to allow users to add key/value data to objects.
  :redmine:`8065`
- Added ``pulp_label_select`` filter to allow users to filter by labels.
  :redmine:`8067`
- Added optional headers field to the aiohttp ClientSession.
  :redmine:`8083`
- Allow querying names on the api using name__icontains, name__contains and name__startswith query parameters.
  :redmine:`8094`
- Added RBAC to the endpoint for managing groups.
  :redmine:`8159`
- Added RBAC to the endpoint for managing group users.
  :redmine:`8160`
- Added the ``AccessPolicy.customized`` field which if ``True`` indicates a user has modified the
  default AccessPolicy.
  :redmine:`8182`
- Added filtering for access policies.
  :redmine:`8189`
- As an authenticated user I can create and view artifacts.
  :redmine:`8193`


Bugfixes
~~~~~~~~

- Fixed bug where duplicate artifact error message was nondeterministic in displaying different error
  messages with different checksum types. Also, updated duplicate artifact error message to be more
  descriptive.
  :redmine:`3387`
- Fixed Pulp import/export bug that occurs when sha384 or sha512 is not in ``ALLOWED_CONTENT_CHECKSUMS``.
  :redmine:`7836`
- X-CSRFToken is not sent through ajax requests (PUT) in api.html. Fixed by setting the right value in
  the JS code.
  :redmine:`7888`
- Provide a mechanism to automatically resolve issues and prevent deadlocks when Redis experiences data loss (such as a restart).
  :redmine:`7912`
- Silence unnecessary log messages from django_guid which were spamming up the logs.
  :redmine:`7982`
- Changed the default permission class to ``IsAdminUser`` to protect endpoints not yet guarded by an access policy from users without permission.
  :redmine:`8018`
- Fixed apidoc bug, where model and object permissions on groups overlapped.
  :redmine:`8033`
- Fixed the viewset_name used by access policy for the cases when parent_viewset is involved.
  :redmine:`8152`
- Made the viewset_name property of access policies read only.
  :redmine:`8185`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added a description of the common filesystem layout in the deployment section.
  :redmine:`7750`
- Updated the reference to the new location of pulplift at the installer repository in the development section.
  :redmine:`7878`
- Add links to plugin docs into docs.pulpproject.org.
  :redmine:`8131`
- Added documentation for labels.
  :redmine:`8157`


Misc
~~~~

- :redmine:`8203`


Plugin API
----------

Features
~~~~~~~~

- Add ``rate_limit`` option to ``Remote``
  :redmine:`7965`
- Made DistributionFilter accessible to plugin writers.
  :redmine:`8059`
- Adding ``Label`` and ``LabelSerializer`` to the plugin api.
  :redmine:`8065`
- Added ``LabelSelectFilter`` to filter resources by labels.
  :redmine:`8067`
- Added ReadOnlyRepositoryViewset to the plugin API.
  :redmine:`8103`
- Added NAME_FILTER_OPTIONS to the plugin API to gain more consistency across plugins when filter by name or similar CharFields.
  :redmine:`8117`
- Added `has_repo_attr_obj_perms` and `has_repo_attr_model_or_obj_perms` to the global access checks available to all plugins to use.
  :redmine:`8161`


Removals
~~~~~~~~

- Plugins are required to define a ``version`` attribute on their subclass of
  ``PulpPluginAppConfig``. Starting with pulpcore==3.10, if undefined while Pulp loads, Pulp will
  refuse to start.
  :redmine:`7930`
- Changed the default permission class to from ``IsAuthenticated`` to ``IsAdminUser``.
  Any endpoints that should be accessible by all known to the system users need to specify the permission_classes accordingly.
  :redmine:`8018`
- ``pulpcore.plugin.models.UnsupportedDigestValidationError`` has been removed. Plugins should
  look for this at ``pulpcore.plugin.exceptions.UnsupportedDigestValidationError`` instead.
  :redmine:`8169`


Deprecations
~~~~~~~~~~~~

- Access to the path of the public key of a signing service was deprecated. The value of the public
  key is now expected to be saved in the model instance as ``SigningService.public_key``.
  :redmine:`7700`
- The ``pulpcore.plugin.storage.get_plugin_storage_path()`` method has been deprecated.
  :redmine:`7935`


3.9.1 (2021-01-21)
==================
REST API
--------

Removals
~~~~~~~~

- CHUNKED_UPLOAD_DIR was converted to a relative path inside MEDIA_ROOT.
  :redmine:`8099`

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
  :redmine:`4498`
- Add support for logging messages with a correlation id that can either be autogenerated or passed in
  with a ``Correlation-ID`` header. This feature is provided as a tech preview in pulpcore 3.9.
  :redmine:`4689`
- Added progress reporting for pulp imports.
  :redmine:`6559`
- Exposed ``aiohttp.ClientTimeout`` fields in ``Remote`` as ``connect_timeout``,
  ``sock_connect_timeout``, ``sock_read_timeout``, and ``total_timeout``.

  This replaces the previous hard-coded 600 second timeout for sock_connect and sock_read,
  giving per-``Remote`` control of all four ``ClientTimeout`` fields to the user.
  :redmine:`7201`
- Enabled users to add checksums to ALLOWED_CONTENT_CHECKSUMS by allowing them to populate checksums
  with handle-artifact-checksums command.
  :redmine:`7561`
- Added version information to api docs.
  :redmine:`7569`
- Made signing services to be immutable. This requires content signers to create a new signing
  service explicitly when a change occurs.
  :redmine:`7701`
- Added support for repairing Pulp by detecting and redownloading missing or corrupted artifact files. Sending a POST request to ``/pulp/api/v3/repair/`` will trigger a task that scans all artifacts for missing and corrupted files in Pulp storage, and will attempt to redownload them from the original remote. Specifying ``verify_checksums=False`` when POSTing to the same endpoint will skip checking the hashes of the files (corruption detection) and will instead just look for missing files.

  The ``verify_checksums`` POST parameter was added to the existing "repository version repair" endpoint as well.
  :redmine:`7755`
- Added check to prevent Pulp to start if there are Artifacts with forbidden checksums.
  :redmine:`7914`


Bugfixes
~~~~~~~~

- Fixed a serious bug data integrity bug where some Artifact files could be silently deleted from storage in specific circumstances.
  :redmine:`7676`
- Moved the initial creation of access_policies to post_migrate signal.
  This enforces their existance both with migrate and flush.
  :redmine:`7710`
- Fixed incremental export to happen if start_version provided, even if last_export is null.
  :redmine:`7716`
- Fixed a file descriptor leak during repository version repair operations.
  :redmine:`7735`
- Fixed bug where exporter directory existed and was writable but not owned by worker process and thus
  not chmod-able.
  :redmine:`7829`
- Properly namespaced the `viewset_name` in `AccessPolicy` to avoid naming conflicts in plugins.
  :redmine:`7845`
- Update jquery version from 3.3.1 to 3.5.1 in API.html template. It is the version provided by djangorestframework~=3.12.2
  :redmine:`7850`
- Prevented a Redis failure scenario from causing the tasking system to back up due to "tasking system
  locks" not being released, even on worker restart.
  :redmine:`7907`
- Use subclassed plugin downloaders during the pulp repair.
  :redmine:`7909`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added requirement to record a demo with PRs of substantial change.
  :redmine:`7703`
- Removed outdated reference stating Pulp did not have an SELinux policy.
  :redmine:`7793`


Removals
~~~~~~~~

- The local file system directory used for uploaded chunks is specified by the setting
  CHUNKED_UPLOAD_DIR. Users are encouraged to remove all uncommitted uploaded files before
  applying this change.
  :redmine:`4498`


Misc
~~~~

- :redmine:`7690`, :redmine:`7753`, :redmine:`7902`, :redmine:`7890`

Plugin API
----------

Features
~~~~~~~~

- Added pre_save hook to Artifact to enforce checksum rules implied by ALLOWED_CONTENT_CHECKSUMS.
  :redmine:`7696`
- Enabled plugin writers to retrieve a request object from a serializer when look ups are
  performed from within the task serializer.
  :redmine:`7718`
- Expose ProgressReportSerializer through `pulpcore.plugin`
  :redmine:`7759`
- Allowed plugin writers to access the models Upload and UploadChunk
  :redmine:`7833`
- Exposed ``pulpcore.plugin.constants.ALL_KNOWN_CONTENT_CHECKSUMS``.
  :redmine:`7897`
- Added ``UnsupportedDigestValidationError`` to ``pulpcore.plugins.exceptions``. Going
  forward, plugin authors can expect to find all unique exceptions under
  ``pulpcore.plugin.exceptions``.
  :redmine:`7908`


Deprecations
~~~~~~~~~~~~

- Plugins are encouraged to define a ``version`` attribute on their subclass of
  ``PulpPluginAppConfig``. If undefined while Pulp loads a warning is now shown to encourage plugin
  writers to implement this attribute, which will be required starting in pulpcore==3.10.
  :redmine:`6671`
- Using the ViewSet's classname to identify its AccessPolicy has been deprecated and is slated for removal in 3.10.
  Instead the urlpattern is supposed to be used.

  Plugins with existing AccessPolicies should add a data migration to rename their AccessPolicies:

  ::
      access_policy = AccessPolicy.get(viewset_name="MyViewSet")
      access_policy.viewset_name = "objectclass/myplugin/myclass"
      access_policy.save()

  :redmine:`7845`
- The ``pulpcore.plugin.models.UnsupportedDigestValidationError`` is being deprecated and
  will be removed in 3.10.

  It can now be found at ``pulpcore.plugin.exceptions.UnsupportedDigestValidationError``
  instead; please change any code that imports it to access it from its new location.
  :redmine:`7908`


3.8.1 (2020-10-30)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a serious bug data integrity bug where some Artifact files could be silently deleted from storage in specific circumstances. (Backported from :redmine:`7676`)
  :redmine:`7758`


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
  :redmine:`7487`
- Django admin site URL is configurable via `ADMIN_SITE_URL` settings parameter.
  :redmine:`7637`
- Always set a default for DJANGO_SETTINGS_MODULE. This means the services files don't need to.
  :redmine:`7720`


Bugfixes
~~~~~~~~

- Fix a warning inappropriately logged when cancelling a task.
  :redmine:`4559`
- When a task is canceled, we now set the state of all incomplete "progress reports" to canceled as well.
  :redmine:`4921`
- Properly handle duplicate content during synchronization and migration from Pulp 2 to 3.
  :redmine:`7147`
- Enable content streaming for RepositoryVersionDistribution
  :redmine:`7568`
- Change dropped DRF filter to django urlize.
  :redmine:`7634`
- Added some more files to MANIFEST.in.
  :redmine:`7656`
- Updated dynaconf requirement to prevent use of older buggy versions.
  :redmine:`7682`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updated examples of auto-distribution.
  :redmine:`5247`
- Improved testing section in Pulp contributor docs.
  Mentioned `prestart`, `pminio`, `pfixtures` and `phelp`.
  :redmine:`7475`
- Fix an erroneous API endpoint in the "upload and publish" workflow documentation.
  :redmine:`7655`
- Documented that we don't support backporting migrations.
  :redmine:`7657`


Plugin API
----------

Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Removed mentions of semver in the plugin API docs, and replaced them with a link to the deprecation policy where appropriate.
  :redmine:`7555`


3.7.9 (2021-11-30)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Prevented a Redis failure scenario from causing the tasking system to back up due to "tasking system
  locks" not being released, even on worker restart.
  (backported from #7907)
  :redmine:`9547`
- Prevent proxy credentials to be passed to aiohttp, so they no longer appear in stack traces.
  This is a rewritten backport of #8167.
  :redmine:`9573`


Plugin API
----------

No significant changes.


3.7.8 (2021-08-24)
==================
REST API
--------

Bugfixes
~~~~~~~~

- In stages-pipeline and new-version sanity-checks, added full error-info on path-problems.
  (backported from #8133)
  :redmine:`9227`


Plugin API
----------

Bugfixes
~~~~~~~~

- Added kwarg to RemoteArtifactSaver init to allow enabling handling of rare error edge-case.

  `fix_mismatched_remote_artifacts=True` enables workaround for a failure-scenario that
  (so far) is only encountered by pulp_rpm. Current behavior is the default.
  (backported from #8133)
  :redmine:`9227`


3.7.7 (2021-07-26)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a bug, where new tasks were assigned to dead workers.
  (backported from #8779)
  :redmine:`9118`


Plugin API
----------

No significant changes.


3.7.6 (2021-04-29)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Backported a fix for on-demand sync/migration of repositories that don't have sha256 checksums.
  :redmine:`8651`


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
  :redmine:`8485`
- Allowed to use PyYAML 5.4 which contains a patch for `CVE-2020-14343 <https://nvd.nist.gov/vuln/detail/CVE-2020-14343`.
  :redmine:`8540`


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
  :redmine:`8373`


Plugin API
----------

No significant changes.


3.7.3 (2020-10-28)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a serious bug data integrity bug where some Artifact files could be silently deleted from storage in specific circumstances. (Backported from :redmine:`7676`)
  :redmine:`7757`


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
  :redmine:`7702`
- Fixed incremental export to happen if start_version provided, even if last_export is null.
  :redmine:`7725`


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
  :redmine:`7610`


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
  :redmine:`5216`
- Added progress-reports to the PulpExport task.
  :redmine:`6541`
- Improve performance and memory consumption of orphan cleanup.
  :redmine:`6581`
- Extra require: s3, azure, prometheus and test
  :redmine:`6844`
- Added the toc_info attribute with filename/sha256sum to PulpExport, to enable direct access to the export-TOC.
  :redmine:`7221`
- Taught export-process to clean up broken files if the export fails.
  :redmine:`7246`
- Added the django-cleanup handlers for removing files stored within FileField
  :redmine:`7316`
- Added deprecations section to the changelog.
  :redmine:`7415`


Bugfixes
~~~~~~~~

- Address some problems with stuck tasks when connection to redis is interrupted.
  :redmine:`6449`
- Fixed a bug where creating an incomplete repository version (via canceled or failed task) could cause future operations to fail.
  :redmine:`6463`
- Added validation for unknown serializers' fields
  :redmine:`7245`
- Fixed: `PulpTemporaryFile` stored in the wrong location
  :redmine:`7319`
- Fixed an edge case where canceled tasks might sometimes be processed and marked completed.
  :redmine:`7389`
- Fixed pulp-export scenario where specifying full= could fail silently.
  :redmine:`7403`
- Fixed OpenAPI creation response status code to 201
  :redmine:`7444`
- The ``AccessPolicy.permissions_assignment`` can now be null, which some viewset endpoints may
  require.
  :redmine:`7448`
- Taught export to insure export-dir was writeable by group as well as owner.
  :redmine:`7459`
- Fixed orphan cleanup for subrepositories (e.g. an add-on repository in RPM distribution tree repository).
  :redmine:`7460`
- Fixed issue with reserved resources not being displayed for waiting tasks.
  :redmine:`7497`
- Fixed broken bindings resulting from drf-spectacular 0.9.13 release.
  :redmine:`7510`
- Fix filesystem exports failing due to undefinied ``validate_path`` method.
  :redmine:`7521`
- Fix a bug that prevented users from adding permissions for models have conflicting names across different django apps.
  :redmine:`7541`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added pulp 2 obsolete concepts (consumers, applicability).
  :redmine:`6255`


Misc
~~~~

- :redmine:`7508`


Plugin API
----------

Features
~~~~~~~~

- Enabled the automatic removal of files, which are stored in FileField, when a corresponding
  model's delete() method is invoked
  :redmine:`7316`
- Add add_and_remove task to pulpcore.plugin.tasking
  :redmine:`7351`
- Added deprecations section to the plugin api changelog.
  :redmine:`7415`


Bugfixes
~~~~~~~~

- The ``AccessPolicy.permissions_assignment`` can now be null, which some viewset endpoints may
  require.
  :redmine:`7448`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Added an example how to use a serializer to create validated objects.
  :redmine:`5927`
- Document the URLField OpenAPI issue
  :redmine:`6828`
- Added all exported models to the autogenerated API reference.
  :redmine:`7045`
- Updated docs recommending plugins to rely on a 1-release deprecation process for backwards
  incompatible changes in the ``pulpcore.plugin``.
  :redmine:`7413`
- Adds plugin writer docs on how to ship snippets which override default webserver routes provided by
  the installer.
  :redmine:`7471`
- Revises the "installation plugin custom tasks" documentation to reflect that plugin writers can
  contribute their custom installation needs directly to the installer.
  :redmine:`7523`


Misc
~~~~

- :redmine:`7270`


3.6.5 (2020-10-28)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed a bug where creating an incomplete repository version (via canceled or failed task) could cause future operations to fail. (Backported from :redmine:`6463`)
  :redmine:`7737`


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
  :redmine:`7510`


Plugin API
----------

No significant changes.


3.6.3 (2020-09-04)
==================
REST API
--------

Misc
~~~~

- :redmine:`7450`


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
  :redmine:`7446`


3.6.1 (2020-09-01)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixing groups API validation
  :redmine:`7329`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updated Pypi installation step.
  :redmine:`6305`
- Added hardware requirements.
  :redmine:`6856`


Misc
~~~~

- :redmine:`7229`


Plugin API
----------

Bugfixes
~~~~~~~~

- Fix custom operation_id's from OpenAPI
  :redmine:`7341`
- OpenAPI: do not discard components without properties
  :redmine:`7347`


3.6.0 (2020-08-13)
==================
REST API
--------

Features
~~~~~~~~

- Added table-of-contents to export and gave import a toc= to find/reassemble pieces on import.
  :redmine:`6737`
- Added ability to associate a Remote with a Repository so users no longer have to specify Remote when
  syncing.
  :redmine:`7015`
- The `/pulp/api/v3/access_policies/` endpoint is available for reading and modifying the AccessPolicy
  used for Role Based Access Control for all Pulp endpoints. This allows for complete customization
  of the Authorization policies.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  :redmine:`7160`
- The `/pulp/api/v3/access_policies/` endpoint also includes a `permissions_assignment` section which
  customizes the permissions assigned to new objects. This allows for complete customization for how
  new objects work with custom define Authorization policies.
  :redmine:`7210`
- The `/pulp/api/v3/users/` endpoint is available for reading the Users, Group membership, and
  Permissions.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  :redmine:`7231`
- The `/pulp/api/v3/groups/` endpoint is available for reading the Groups, membership, and
  Permissions.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  :redmine:`7232`
- The `/pulp/api/v3/tasks/` endpoint now provides a user-isolation behavior for non-admin users. This
  policy is controllable at the `/pulp/api/v3/access_policies/` endpoint.

  NOTE: The user-isolation behavior is in "tech preview" and production systems are recommended to
  continue using the build-in ``admin`` user only.
  :redmine:`7301`
- Extended endpoint `/pulp/api/v3/groups/:pk/users` to add and remove users from a group.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  :redmine:`7310`
- Extended endpoints `/pulp/api/v3/groups/:pk/model_permissions` and
  `/pulp/api/v3/groups/:pk/object_permissions` to add and remove permissions from a group.

  NOTE: this endpoint is in tech-preview and may change in backwards incompatible ways in the future.
  :redmine:`7311`


Bugfixes
~~~~~~~~

- WorkerDirectory.delete() no longer recursively trys to delete itself when encountering a permission error
  :redmine:`6504`
- Stopped preventing removal of PulpExport/Exporter when last-export existed.
  :redmine:`6555`
- First time on demand content requests appear in the access log.
  :redmine:`7002`
- Fixed denial of service caused by extra slashes in content urls.
  :redmine:`7066`
- Set a default DJANGO_SETTINGS_MODULE env var in content app
  :redmine:`7179`
- Added plugin namespace to openapi href identifier.
  :redmine:`7209`
- By default, html in field descriptions filtered out in REST API docs unless 'include_html' is set.
  :redmine:`7299`
- Fixed plugin filtering in bindings to work independently from "bindings" parameter.
  :redmine:`7306`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Made password variable consistent with Ansible installer example playbook
  :redmine:`7065`
- Fixed various docs bugs in the pulpcore docs.
  :redmine:`7090`
- Adds documentation about SSL configuration requirements for reverse proxies.
  :redmine:`7285`
- Fixed REST API docs.
  :redmine:`7292`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removed unnecessary fields from the import/export transfer.
  :redmine:`6515`
- Upgrading the api documentation from OpenAPI v2 to OpenAPI v3.
  - Methods signatures for bindings may change.
  :redmine:`7108`
- Changed default ``download_concurrency`` on Remotes from 20 to 10 to avoid connection problems. Also
  updated existing Remotes with ``download_concurrency`` of 20 to 10.
  :redmine:`7212`


Misc
~~~~

- :redmine:`6807`, :redmine:`7142`, :redmine:`7196`


Plugin API
----------

Features
~~~~~~~~

- Adding `PulpTemporaryFile` for handling temporary files between the viewset and triggered tasks
  :redmine:`6749`
- ``RepositorySyncURLSerializer`` will now check remote on the repository before it raises an
  exception if the remote param is not set.
  :redmine:`7015`
- Added a hook on ``Repository`` called ``artifacts_for_version()`` that plugins can override to
  modify the logic behind ``RepositoryVersion.artifacts``. For now, this is used when exporting
  artifacts.
  :redmine:`7021`
- Enabling plugin writers to have more control on `HttpDownloader` response codes 400+
  by subclassing `HttpDownloader` and overwriting `raise_for_status` method
  :redmine:`7117`
- `BaseModel` now inherits from `LifecycleModel` provided by `django-lifecycle` allowing any subclass
  to also use it instead of signals.
  :redmine:`7151`
- A new `pulpcore.plugin.models.AutoDeleteObjPermsMixin` object can be added to models to
  automatically delete all user and group permissions for an object just before the object is deleted.
  This provides an easy cleanup mechanism and can be added to models as a mixin. Note that your model
  must support `django-lifecycle` to use this mixin.
  :redmine:`7157`
- A new model `pulpcore.plugin.models.AccessPolicy` is available to store AccessPolicy statements in
  the database. The model's `statements` field stores the list of policy statements as a JSON field.
  The `name` field stores the name of the Viewset the `AccessPolicy` is protecting.

  Additionally, the `pulpcore.plugin.access_policy.AccessPolicyFromDB` is a drf-access-policy which
  viewsets can use to protect their viewsets with. See the :ref:`viewset_enforcement` for more
  information on this.
  :redmine:`7158`
- Adds the `TaskViewSet` and `TaskGroupViewSet` objects to the plugin api.
  :redmine:`7187`
- Enabled plugin writers to create immutable repository ViewSets
  :redmine:`7191`
- A new `pulpcore.plugin.models.AutoAddObjPermsMixin` object can be added to models to automatically
  add permissions for an object just after the object is created. This is controlled by data saved in
  the `permissions_assignment` attribute of the `pulpcore.plugin.models.AccessPolicy` allowing users
  to control what permissions are created. Note that your model must support `django-lifecycle` to use
  this mixin.
  :redmine:`7210`
- Added ability for plugin writers to set a ``content_mapping`` property on content resources to
  provide a custom mapping of content to repositories.
  :redmine:`7252`
- Automatically excluding ``pulp_id``, ``pulp_created``, and ``pulp_last_updated`` for
  ``QueryModelResources``.
  :redmine:`7277`
- Viewsets that subclass ``pulpcore.plugin.viewsets.NamedModelViewSet` can declare the
  ``queryset_filtering_required_permission`` class attribute naming the permission required to view
  an object. See the :ref:`queryset_scoping` documentation for more information.
  :redmine:`7300`


Bugfixes
~~~~~~~~

- Making operation_id unique
  :redmine:`7233`
- Making ReDoc OpenAPI summary human readable
  :redmine:`7237`
- OpenAPI schema generation from CLI
  :redmine:`7258`
- Allow `pulpcore.plugin.models.AutoAddObjPermsMixin.add_for_object_creator` to skip assignment of
  permissions if there is no known user. This allows endpoints that do not use authorization but still
  create objects in the DB to execute without error.
  :redmine:`7312`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Omit a view/viewset from the OpenAPI schema
  :redmine:`7133`
- Added plugin writer docs for ``BaseContentResource``.
  :redmine:`7296`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Newlines in certificate string (ca_cert, client_cert, client_key) on Remotes are not required to be escaped.
  :redmine:`6735`
- Replaced drf-yasg with drf-spectacular.
  - This updates the api documentation to openapi v3.
  - Plugins may require changes.
  - Methods signatures for bindings may change.
  :redmine:`7108`
- Moving containers from pulpcore to pulp-operator
  :redmine:`7171`


3.5.0 (2020-07-08)
==================
REST API
--------

Features
~~~~~~~~

- Added start_versions= to export to allow for arbitrary incremental exports.
  :redmine:`6763`
- Added GroupProgressReport to track progress in a TaskGroup.
  :redmine:`6858`
- Provide a user agent string with all aiohttp requests by default.
  :redmine:`6954`


Bugfixes
~~~~~~~~

- Fixed 'integer out of range' error during sync by changing RemoteArtifact size field to BigIntegerField.
  :redmine:`6717`
- Added a more descriptive error message that is shown when CONTENT_ORIGIN is not properly configured
  :redmine:`6771`
- Including requirements.txt on MANIFEST.in
  :redmine:`6888`
- Corrected a number of filters to be django-filter-2.3.0-compliant.
  :redmine:`6915`
- Locked Content table to prevent import-deadlock.
  :redmine:`7073`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updating installation docs
  :redmine:`6836`
- Fixed a number of typos in the import/export workflow docs.
  :redmine:`6919`
- Fixed docs which claim that admin user has a default password.
  :redmine:`6992`
- Fixed broken link to content plugins web page
  :redmine:`7017`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removes the Write models from the OpenAPI schema.
  Brings back the models that were accidentally removed from the OpenAPI schema in 3.4.0 release.
  :redmine:`7087`


Misc
~~~~

- :redmine:`6483`, :redmine:`6925`


Plugin API
----------

Features
~~~~~~~~

- Views can specify the tag name with `pulp_tag_name`
  :redmine:`6832`
- Added GroupProgressReport to track progress in a TaskGroup.
  :redmine:`6858`
- Exported the symbols `serializers.SingleContentArtifactField` and `files.PulpTemporaryUploadedFile`.
  :redmine:`7088`


----


3.4.1 (2020-06-03)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Including requirements.txt on MANIFEST.in
  :redmine:`6888`


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
  :redmine:`6136`
- Added support for S3 and other non-filesystem storage options to pulp import/export functionality.
  :redmine:`6456`
- Optimized imports by having repository versions processed using child tasks.
  :redmine:`6484`
- Added repository type check during Pulp imports.
  :redmine:`6532`
- Added version checking to import process.
  :redmine:`6558`
- Taught PulpExport to export by RepositoryVersions if specified.
  :redmine:`6566`
- Task groups now have an 'all_tasks_dispatched' field which denotes that no more tasks will spawn
  as part of this group.
  :redmine:`6591`
- Taught export how to split export-file into chunk_size bytes.
  :redmine:`6736`


Bugfixes
~~~~~~~~

- Remote fields `username` and `password` show up in:
  REST docs, API responses, and are available in the bindings.
  :redmine:`6346`
- Fixed a bug, where the attempt to cancel a completed task lead to a strange response.
  :redmine:`6465`
- Fixed KeyError during OpenAPI schema generation.
  :redmine:`6468`
- Added a missing trailing slash to distribution's base_url
  :redmine:`6507`
- Fixed a bug where the wrong kind of error was being raised for href parameters of mismatched types.
  :redmine:`6521`
- containers: Fix pulp_rpm 3.3.0 install by replacing the python3-createrepo_c RPM with its build-dependencies, so createrep_c gets installed & built from PyPI
  :redmine:`6523`
- Fixed OpenAPI schema for importer and export APIs.
  :redmine:`6556`
- Normalized export-file-path for PulpExports.
  :redmine:`6564`
- Changed repository viewset to use the general_update and general_delete tasks.
  This fixes a bug where updating specialized fields of a repository was impossible due to using the wrong serializer.
  :redmine:`6569`
- Only uses multipart OpenAPI Schema when dealing with `file` fields
  :redmine:`6702`
- Fixed a bug that prevented write_only fields from being present in the API docs and bindings
  :redmine:`6775`
- Added proper headers for index.html pages served by content app.
  :redmine:`6802`
- Removed Content-Encoding header from pulpcore-content responses.
  :redmine:`6831`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Adding docs for importing and exporting from Pulp to Pulp.
  :redmine:`6364`
- Add some documentation around TaskGroups.
  :redmine:`6641`
- Introduced a brief explanation about `pulp_installer`
  :redmine:`6674`
- Added a warning that the REST API is not safe for multi-user use until RBAC is implemented.
  :redmine:`6692`
- Updated the required roles names
  :redmine:`6758`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed repositories field on ``/pulp/api/v3/exporters/core/pulp/`` from UUIDs to hrefs.
  :redmine:`6457`
- Imports now spawn child tasks which can be fetched via the ``child_tasks`` field of the import task.
  :redmine:`6484`
- Content of ssl certificates and keys changed to be return their full value instead of sha256 through REST API.
  :redmine:`6691`
- Replaced PulpExport filename/sha256 fields, with output_info_file, a '<filename>': '<hash>' dictionary.
  :redmine:`6736`


Misc
~~~~

- :redmine:`5020`, :redmine:`6421`, :redmine:`6477`, :redmine:`6539`, :redmine:`6542`, :redmine:`6544`, :redmine:`6572`, :redmine:`6583`, :redmine:`6695`, :redmine:`6803`, :redmine:`6804`


Plugin API
----------

Features
~~~~~~~~

- Added new NoArtifactContentUploadSerializer and NoArtifactContentUploadViewSet to enable plugin
  writers to upload content without storing an Artifact
  :redmine:`6281`
- Added view_name_pattern to DetailRelatedField and DetailIdentityField to properly identify wrong resource types.
  :redmine:`6521`
- Added support for Distributions to provide non-Artifact content via a content_handler.
  :redmine:`6570`
- Added constants to the plugin API at ``pulpcore.plugin.constants``.
  :redmine:`6579`
- TaskGroups now have an 'all_tasks_dispatched' field that can be used to notify systems that no
  further tasks will be dispatched for a TaskGroup. Plugin writers should call ".finish()" on all
  TaskGroups created once they are done using them to set this field.
  :redmine:`6591`


Bugfixes
~~~~~~~~

- Added ``RemoteFilter`` to the plugin API as it was missing but used by plugin_template.
  :redmine:`6563`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Fields: `username` and `password` will be returned to the rest API user requesting a `Remote`
  :redmine:`6346`
- Rehomed QueryModelResource to pulpcore.plugin.importexport.
  :redmine:`6514`
- The :meth:`pulpcore.content.handler.Handler.list_directory` function now returns a set of strings where it returned a string of HTML before.
  :redmine:`6570`


----


3.3.1 (2020-05-07)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fixed partial and general update calls for SecretCharField on the Remote.
  :redmine:`6565`
- Fixed bug where ``TaskGroup`` was showing up as null for ``created_resources`` in tasks.
  :redmine:`6573`


Plugin API
----------

Features
~~~~~~~~

- Add TaskGroup to the plugin API.
  :redmine:`6603`


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
  :redmine:`5613`
- Added support for exporting pulp-repo-versions. POSTing to an exporter using the
  ``/pulp/api/v3/exporters/core/pulp/<exporter-uuid>/exports/`` API will instantiate a
  PulpExport entity, which will generate an export-tar.gz file at
  ``<exporter.path>/export-<export-uuid>-YYYYMMDD_hhMM.tar.gz``
  :redmine:`6135`
- Added API for importing Pulp Exports at ``POST /importers/core/pulp/<uuid>/imports/``.
  :redmine:`6137`
- Added the new setting CHUNKED_UPLOAD_DIR for configuring a default directory used for uploads
  :redmine:`6253`
- Exported SigningService in plugin api
  :redmine:`6256`
- Added name filter for SigningService
  :redmine:`6257`
- Relationships between tasks that spawn other tasks will be shown in the Task API.
  :redmine:`6282`
- Added a new APIs for PulpExporters and Exports at ``/exporters/core/pulp/`` and
  ``/exporters/core/pulp/<uuid>/exports/``.
  :redmine:`6328`
- Added PulpImporter API at ``/pulp/api/v3/importers/core/pulp/``. PulpImporters are used for
  importing exports from Pulp.
  :redmine:`6329`
- Added an ``ALLOWED_EXPORT_PATHS`` setting with list of filesystem locations that exporters can export to.
  :redmine:`6335`
- Indroduced `ordering` keyword, which orders the results by specified field.
  Pulp objects will by default be ordered by pulp_created if that field exists.
  :redmine:`6347`
- Task Groups added -- Plugin writers can spawn tasks as part of a "task group",
  which facilitates easier monitoring of related tasks.
  :redmine:`6414`


Bugfixes
~~~~~~~~

- Improved the overall performance while syncing very large repositories
  :redmine:`6121`
- Made chunked uploads to be stored in a local file system instead of a default file storage
  :redmine:`6253`
- Fixed 500 error when calling modify on nonexistent repo.
  :redmine:`6284`
- Fixed bug where user could delete repository version 0 but not recreate it by preventing users from
  deleting repo version 0.
  :redmine:`6308`
- Fixed non unique content units on content list
  :redmine:`6347`
- Properly sort endpoints during generation of the OpenAPI schema.
  :redmine:`6372`
- Improved resync performance by up to 2x with a change to the content stages.
  :redmine:`6373`
- Fixed bug where 'secret' fields would be set to the sha256 checksum of the original value.
  :redmine:`6402`
- Fixed pulp containers not allowing commands to be run via absolute path.
  :redmine:`6420`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Documented bindings installation for a dev environment
  :redmine:`6221`
- Added documentation for how to write changelog messages.
  :redmine:`6336`
- Cleared up a line in the database settings documentation that was ambiguous.
  :redmine:`6384`
- Updated docs to reflect that S3/Azure are supported and no longer tech preview.
  :redmine:`6443`
- Added tech preview note to docs for importers/exporters.
  :redmine:`6454`
- Renamed ansible-pulp to pulp_installer (to avoid confusion with pulp-ansible)
  :redmine:`6461`
- Fixed missing terms in documentation.
  :redmine:`6485`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Changing STATIC_URL from `/static/` to `/assets/` for avoiding conflicts
  :redmine:`6128`
- Exporting now requires the configuration of the ``ALLOWED_EXPORT_PATHS`` setting.  Without this
  configuration, Pulp will not export content to the filesystem.
  :redmine:`6335`


Misc
~~~~

- :redmine:`5826`, :redmine:`6155`, :redmine:`6357`, :redmine:`6450`, :redmine:`6451`, :redmine:`6481`, :redmine:`6482`


Plugin API
----------

Features
~~~~~~~~

- Tasks can now be spawned from inside other tasks, and these relationships can be explored
  via the "parent_task" field and "child_tasks" related name on the Task model.
  :redmine:`6282`
- Added a new Export model, serializer, and viewset.
  :redmine:`6328`
- Added models Import and Importer (as well as serializers and viewsets) that can be used for
  importing data into Pulp.
  :redmine:`6329`
- `NamedModelViewSet` uses a default ordering of `-pulp_created` using the `StableOrderingFilter`.
  Users using the `ordering` keyword will be the primary ordering used when specified.
  :redmine:`6347`
- Added two new repo validation methods (validate_repo_version and validate_duplicate_content).
  :redmine:`6362`
- enqueue_with_reservation() provides a new optional argument for "task_group".
  :redmine:`6414`


Bugfixes
~~~~~~~~

- Fixed bug where RepositoryVersion.artifacts returns None.
  :redmine:`6439`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Add plugin writer docs on adding MANIFEST.in entry to include ``webserver_snippets`` in the Python
  package.
  :redmine:`6249`
- Updated the metadata signing plugin writers documentation.
  :redmine:`6342`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Changed master model from FileSystemExporter to Exporter. Plugins will still need to extend
  FileSystemExporter but the master table is now core_exporter. This will require that plugins drop
  and recreate their filesystem exporter tables.
  :redmine:`6328`
- RepositoryVersion add_content no longer checks for duplicate content.
  :redmine:`6362`


Misc
~~~~

- :redmine:`6342`


----


3.2.1 (2020-03-17)
==================
REST API
--------

Misc
~~~~

- :redmine:`6244`


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
  :redmine:`5859`
- Resolve DNS faster with aiodns
  :redmine:`6190`


Bugfixes
~~~~~~~~

- Considering base version when removing duplicates
  :redmine:`5964`
- Renames /var/lib/pulp/static/ to /var/lib/pulp/assets/.
  :redmine:`5995`
- Disabled the trimming of leading and trailing whitespace characters which led to a situation where
  a hash of a certificate computed in Pulp was not equal to a hash generated locally
  :redmine:`6025`
- Repository.latest_version() considering deleted versions
  :redmine:`6147`
- Stopped HttpDownloader sending basic auth credentials to redirect location if domains don't match.
  :redmine:`6227`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Updated docs to suggest to use ``pulpcore-manager`` command instead of ``django-admin`` directly.
  :redmine:`5859`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Renaming Repository.last_version to Repository.next_version
  :redmine:`6147`


Misc
~~~~

- :redmine:`6038`, :redmine:`6202`


Plugin API
----------

Features
~~~~~~~~

- Adding not equal lookup to model field filters.
  :redmine:`5868`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Adds plugin writer docs on adding custom url routes and having the installer configure the reverse
  proxy to route them.
  :redmine:`6209`


----


3.1.1 (2020-02-17)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Content with duplicate repo_key_fields raises an error
  :redmine:`5567`
- Resolve content app errors ``django.db.utils.InterfaceError: connection already closed``.
  :redmine:`6045`
- Fix a bug that could cause an inability to detect an invalid signing script during the validation
  :redmine:`6077`
- Fixing broken S3 redirect
  :redmine:`6154`
- Pin `idna==2.8`` to avoid a version conflict caused by the idna 2.9 release.
  :redmine:`6169`


Plugin API
----------

Features
~~~~~~~~

- A new method ``_reset_db_connection`` has been added to ``content.Handler``. It can be called before
  accessing the db to ensure that the db connection is alive.
  :redmine:`6045`


----


3.1.0 (2020-01-30)
==================
REST API
--------

Features
~~~~~~~~

- Allow administrators to add a signing service
  :redmine:`5943`
- Adds ``pulpcore.app.authentication.PulpDoNotCreateUsersRemoteUserBackend`` which can be used to
  verify authentication in the webserver, but will not automatically create users like
  ``django.contrib.auth.backends.RemoteUserBackend`` does.
  :redmine:`5949`
- Allow Azure blob storage to be used as DEFAULT_FILE_STORAGE for Pulp
  :redmine:`5954`
- Allow to filter publications by ``repository_version`` and ``pulp_created``
  :redmine:`5968`
- Adds the ``ALLOWED_IMPORT_PATHS`` setting which can specify the file path prefix that ``file:///``
  remote paths can import from.
  :redmine:`5974`
- Allow the same artifact to be published at multiple relative paths in the same publication.
  :redmine:`6037`


Bugfixes
~~~~~~~~

- Files stored on S3 and Azure now download with the correct filename.
  :redmine:`4733`
- Adds operation_summary to the OpenAPI schema definition of repository modify operation
  :redmine:`6002`
- Temporarily pinned redis-py version to avoid a task locking issue.
  :redmine:`6038`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Rewrote the Authentication page for more clarity on how to configure Pulp's authentication.
  :redmine:`5949`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removed the ``django.contrib.auth.backends.RemoteUserBackend`` as a default configured backend in
  ``settings.AUTHENTICATION_BACKENDS``. Also removed
  ``pulpcore.app.authentication.PulpRemoteUserAuthentication`` from the DRF configuration of
  ``DEFAULT_AUTHENTICATION_CLASSES``.
  :redmine:`5949`
- Importing from file:/// now requires the configuration of the ``ALLOWED_IMPORT_PATHS`` setting.
  Without this configuration, Pulp will not import content from ``file:///`` locations correctly.
  :redmine:`5974`


Misc
~~~~

- :redmine:`5795`


Plugin API
----------

Features
~~~~~~~~

- Allow awaiting for resolution on DeclarativeContent.
  :redmine:`5668`
- Add a previous() method to RepositoryVersion.
  :redmine:`5734`
- Enable plugin writers to sign selected content with signing scripts provided by administrators
  :redmine:`5946`
- Add a batching content iterator ``content_batch_qs()`` to ``RepositoryVersion``.
  :redmine:`6024`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- The ```Handler._handle_file_response` has been removed. It was renamed to
  ``_serve_content_artifact`` and has the following signature::

      def _serve_content_artifact(self, content_artifact, headers):

  :redmine:`4733`
- Remove get_or_create_future and does_batch from DeclarativeContent. Replaced by awaiting for
  resolution on the DeclarativeContent itself.
  :redmine:`5668`


----


3.0.1 (2020-01-15)
==================
REST API
--------

Bugfixes
~~~~~~~~

- Fix bug where content shows as being added and removed in the same version.
  :redmine:`5707`
- Fix bug where calling Repository new_version() outside of task raises exception.
  :redmine:`5894`
- Adjusts setup.py classifier to show 3.0 as Production/Stable.
  :redmine:`5896`
- Importing from file:/// paths no longer destroys the source repository.
  :redmine:`5941`
- Webserver auth no longer prompts for csrf incorrectly.
  :redmine:`5955`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Removed ``pulpcore.app.middleware.PulpRemoteUserMiddleware`` from the default middleware section.
  Also replaced ``rest_framework.authentication.RemoteUserAuthentication`` with
  ``pulpcore.app.authentication.PulpRemoteUserAuthentication`` in the Django Rest Framework portion
  of the config.
  :redmine:`5955`


Misc
~~~~

- :redmine:`5833`, :redmine:`5867`, :redmine:`5870`, :redmine:`5873`


Plugin API
----------

Features
~~~~~~~~

- Added an optional parameter base_version to RepositoryVersion add() and removed() methods.
  :redmine:`5706`


Deprecations and Removals
~~~~~~~~~~~~~~~~~~~~~~~~~

- Saving an Artifact from a source that is outside of settings.MEDIA_ROOT will copy the file instead
  of moving the file as it did in previous versions. This causes data imported from file:/// sources
  to be left in tact.
  :redmine:`5941`


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
  :redmine:`5701`


Bugfixes
~~~~~~~~

- Improve speed and memory performance.
  :redmine:`5688`


Improved Documentation
~~~~~~~~~~~~~~~~~~~~~~

- Fix an incorrect license claim in the docs. Pulp is GPLv2+.
  :redmine:`4592`
- Labeling 3.0 features as tech preview.
  :redmine:`5563`
- Simplified docs index page.
  :redmine:`5714`
- Add text to Promotion page.
  :redmine:`5721`
- Fixes and updates to the glossry page.
  :redmine:`5726`


Plugin API
----------

Features
~~~~~~~~

- Added a new required field called CONTENT_TYPES to the Repository model.
  :redmine:`5701`
