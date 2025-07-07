# Settings

There is one required setting, although specific plugins may have additional required settings.

- `SECRET_KEY <secret-key-setting>`

Pulp uses four types of settings:

- `Django settings` Pulp is configuring
- `Pulp defined settings`
- `Redis settings` Pulp is using
- `Kafka settings`

!!! note
    For more information on how to specify settings see the
    [`Applying Settings`](site:pulpcore/docs/admin/guides/configure-pulp/).


## Django Settings

Below is a list of the most common Django settings Pulp users typically use.
Pulp is a Django project, so any [Django setting] can be set.

### AUTHENTICATION\_BACKENDS

By default, Pulp has two types of authentication enabled, and they fall back for each other:

1. Basic Auth which is checked against an internal users database.
1. Webserver authentication that relies on the webserver to perform the authentication.

To change the authentication types Pulp will use, modify the `AUTHENTICATION_BACKENDS` settings.
See the [Django authentication documentation] for more information.

### DATABASES

By default, Pulp uses PostgreSQL on localhost.
PostgreSQL is the only supported database.
For instructions on how to configure the database, refer to [Django database settings].

### DEFAULT\_FILE\_STORAGE

!!! warning "Deprecated in `3.70`"
    The `DEFAULT_FILE_STORAGE` setting was deprecated in [django 4.2] and will be removed from pulpcore on `3.85`.
    Between `3.70` and `3.85`, replace it with [`STORAGES`](#storages).

### LOGGING

By default, Pulp logs at an INFO level to syslog.
For all possible configurations please refer to [Django documentation on logging].

Enabling DEBUG logging is a common troubleshooting step.
See the [Enabling Debug Logging] documentation for details on how to do that.

### MEDIA\_ROOT

The location where Pulp will store files.
By default, this is `/var/lib/pulp/media`.

This only affects storage location when `STORAGES['default']['BACKEND']` is set to `pulpcore.app.models.storage.FileSystem`.

See the [storage documentation](site:pulpcore/docs/admin/guides/configure-pulp/configure-storages/) for more info.

It should have permissions of:

- mode: 750
- owner: pulp (the account that pulp runs under)
- group: pulp (the group of the account that pulp runs under)
- SELinux context: `system_u:object_r:pulpcore_var_lib_t:s0`

### SECRET\_KEY

In order to get a pulp server up and running a [Django secret key] *must* be provided.
The following code snippet can be used to generate a random `SECRET_KEY`.

```python linenums="1"
import secrets

chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
print(''.join(secrets.choice(chars) for i in range(50)))
```

### STORAGES

!!! note "Added in `3.70`"
    Starting in `3.70`, this should be used in the place of [`DEFAULT_FILE_STORAGE`](#default_file_storage).

Pulp uses [django-storages] to support multiple storage backends.
If no backend is configured, Pulp will by default use the local filesystem (`pulpcore.app.models.storage.FileSystem`).

The storage setting has the form:

```python
STORAGES = {
    "default": {
        "BACKEND": "{storage-class}",
        "OPTIONS": {
            "{option-key}": "{option-value}",
            ...
        },
    },
}
```

To use another backend storage, you'll need to:

1. Set up your storage and gather required credentials and specific configs.
1. Ensure the `django-storage[s3|google|azure]` python package is installed.
This depends on the installation method.
1. Configure the default `BACKEND` storage class.
1. Configure available `OPTIONS` for that backend.

Learn more on the
[Configure Storages](site:pulpcore/docs/admin/guides/configure-pulp/configure-storages/) guide.

Overview of the integration with Pulp:

- **Supported**: We support (test) Amazon S3 and Azure.
- **Untested**: Other backends provided by `django-storages` may work as well, but we provide no guarantee.
- **Known caveat**: Using SFTP Storage is not recommended in Pulp's current state, and doing so can lead to file corruption.
This is because Pulp currently uses coroutines that seem to be incompatible with Django's SFTPStorage implementation.


## Pulp Settings

Pulp defines the following settings itself:

### ALLOWED\_CONTENT\_CHECKSUMS

The list of content-checksums this pulp-instance is **allowed to use**.
By default, the following are used:

```
ALLOWED_CONTENT_CHECKSUMS = ["sha224", "sha256", "sha384", "sha512"]
```

The entire set of supported checksums are:
`md5`, `sha1`, `sha224`, `sha256`, `sha384`, and `sha512`.

!!! warning
    Due to its use as the primary content-identifier, "sha256" **IS REQUIRED**.
    Pulp will fail to start if `"sha256"` is not found in this set.

Pulp can prohibit or allow checksums by setting the `ALLOWED_CONTENT_CHECKSUMS` setting.
Changing this setting requires a few steps.

First, before you change the setting, see how your Pulp instance will be impacted by this change by running:

`pulpcore-manager handle-artifact-checksums --report --checksums sha256,sha512`

Adjust `--checksums` as comma separated list of checksums types to match your needs.

!!! note
    If you already changed `ALLOWED_CONTENT_CHECKSUMS` in pulp settings you can leave out `--checksums`,
    and the checksums will be parsed from Pulp settings.

Before switching, any on-demand repositories containing forbidden checksum digests
need to be synced with `policy=immediate` to populate missing allowed checksums.
This can heavily impact your disk space.
Alternatively, users can remove these offending repository versions followed by orphan cleanup.

If you have artifacts that do not conform to your `ALLOWED_CONTENT_CHECKSUMS` setting, they need to be re-hashed.
You can update them using:

`pulpcore-manager handle-artifact-checksums`

!!! warning
    If Pulp fails to start because forbidden checksums have been identified or required ones are
    missing, run `pulpcore-manager handle-artifact-checksums` command.

### ALLOWED\_EXPORT\_PATHS

One or more real filesystem paths that Exporters can export to.
For example to allow a path of `/mnt/foo/bar/another/folder/` you could specify:

```
ALLOWED_EXPORT_PATHS = ['/mnt/foo/bar']  # only a subpath is needed
```

Defaults to `[]` which means no path is allowed.

### ALLOWED\_IMPORT\_PATHS

One or more real filesystem paths that Remotes with filesystem paths can import from.
For example to allow a remote url of `file:///mnt/foo/bar/another/folder/` you could specify:

```
ALLOWED_IMPORT_PATHS = ['/mnt/foo/bar']  # only a subpath is needed
```

Defaults to `[]`, meaning `file:///` urls are not allowed in any Remote.

### ANALYTICS

If `True`, Pulp will anonymously post analytics information to
[https://analytics.pulpproject.org/](https://analytics.pulpproject.org/) and aids in project decision-making.
See the `analytics docs ` for more info on exactly what is posted along with an example.

Defaults to `True`.

### API\_ROOT

A string containing the prefix for the Pulp API path generated by appending `api/v3/`.
This setting can be used to root the Pulp API in a different namespace on your server.
It must match your reverse proxy configuration and effects hrefs returned from the API.

Defaults to `/pulp/`.
This makes the V3 API by default serve from `/pulp/api/v3/`.

### CACHE\_ENABLED

Store cached responses from the content app into Redis.
This setting improves the performance of the content app under heavy load for similar requests.

Defaults to `False`.

!!! note
    The entire response is not stored in the cache.
    Only the location of the file needed to recreate the response is stored.
    This reduces database queries and allows for many responses to be stored inside the cache.

### CACHE\_SETTINGS

Dictionary with tunable settings for the cache:

- `EXPIRES_TTL` - Number of seconds entries should stay in the cache before expiring.

Defaults to `600` seconds.

!!! note
    Set to `None` to have entries not expire.
    Content app responses are always invalidated when the backing distribution is updated.

### CHUNKED\_UPLOAD\_DIR

A relative path inside the `DEPLOY_ROOT` directory used exclusively for uploaded chunks.
The uploaded chunks are stored in the default storage specified by `STORAGES['default']['BACKEND']`.
This option allows users to customize the actual place where chunked uploads should be stored within the declared storage.
A change to this setting only applies to uploads created after the change.

Defaults to `upload`, which is sufficient for most use cases.

### CONTENT\_APP\_TTL

The number of seconds before a content app should be considered lost.

Defaults to `30` seconds.

### CONTENT\_ORIGIN

A string containing the `protocol`, `fqdn`, and optionally `port` where the content app is reachable by users.
This is used by `pulpcore` and various plugins when referring users to the content app.
For example if the API should redirect users to content at pulp.example.com using HTTPS,
you would set: `https://pulp.example.com` (not including `/pulp/content`, the `CONTENT_PATH_PREFIX`).
Usually this should point to the external address of the reverse proxy.
When set to `None`, the `base_url` for Distributions is a relative path.
This means the API returns relative URLs without the protocol, fqdn, and port.

Default to `None`.

### CONTENT\_PATH\_PREFIX

A string containing the path prefix for the content app.
This is used by the REST API when forming URLs to redirect clients to the content serving app,
and by the content serving application to match incoming URLs.

Defaults to `/pulp/content/`.

### DB\_ENCRYPTION\_KEY

The file location of a symmetric fernet key that Pulp uses to encrypt sensitive fields in the database.
Default location is `/etc/pulp/certs/database_fields.symmetric.key`.

See [Database Encryption] for more details.

### DJANGO\_GUID

Pulp uses `django-guid` to append correlation IDs to logging messages.
For more information on how to configure the `DJANGO_GUID` setting, see the [django-guid settings documentation].
To read more about using correlation id in Pulp, read [our guide](site:pulpcore/docs/user/guides/correlation-id/).

### DOMAIN\_ENABLED

!!! note
    This feature is provided as a tech-preview

Enable the `Domains feature to enable multi-tenancy capabilities <domains>`.
All installed plugins must be Domain compatible for Pulp to start.

Defaults to `False`.

### ENABLED\_PLUGINS

An optional list of plugin names.
If provided, Pulp will limit loading plugins to this list.
If omitted, Pulp will load all installed plugins.

### HIDE\_GUARDED\_DISTRIBUTIONS

If `True`, the distributions, that are protected by a content guard,
will not be shown on the directory listing in the content app.

Defaults to `False`.

### ORPHAN\_PROTECTION\_TIME

The time, specified in minutes, for how long Pulp will hold orphan Content and Artifacts
before they become candidates for deletion by an orphan cleanup task.
This should ideally be longer than your longest running task.
Otherwise any content created during that task could be cleaned up before the task finishes.

Defaults to 1440 minutes (24 hours).

### OTEL\_ENABLED

Toggles the activation of OpenTelemetry instrumentation for monitoring and tracing the application's performance.

Defaults to `False`.

### REDIRECT\_TO\_OBJECT\_STORAGE

When set to `True` access to artifacts is redirected to the corresponding Cloud storage
configured in `STORAGES['default']['BACKEND']` using pre-authenticated URLs.
When set to `False` artifacts are always served by the content app instead.

Defaults to `True`; ignored for local file storage.

### REMOTE\_CONTENT\_FETCH\_FAILURE\_COOLDOWN

In the context of on-demand requests in the Content App,
the time in seconds that a content source from a specific remote will be ignored after failing to download the correct binary from it.
Learn more about [on-demand and streaming limitations].

Defaults to `5` minutes.

### REMOTE\_USER\_ENVIRON\_NAME

The name of the WSGI environment variable to read for [Webserver Auth with Reverse Proxy].
It is only used with the `PulpRemoteUserAuthentication` authentication class.

!!! warning
    Configuring this has serious security implications.
    See the [Django warning at the end of this section in their docs] for more details.

Defaults to `'REMOTE_USER'`.

### REMOTE\_USER\_OPENAPI\_SECURITY\_SCHEME

A JSON object representing the security scheme advertised for the `PulpRemoteUserAuthentication` authentication class.

Defaults to `{"type": "mutualTLS"}`, which represents x509 certificate based authentication.

### TASK\_DIAGNOSTICS

When enabled, users are allowed to request various diagnostics for analysis by a developer.

Administrators can enable support for `["memory", "pyinstrument", "memray"]`.
Any subset of those can be used, or all of them, or none of them.

!!! note
    `memray` and `pyinstrument` diagnostics require additional packages to be installed.

Defaults to `[]` (no diagnostics enabled).

See [task diagnostics documentation] for more details.

### TASK\_GRACE\_INTERVAL

On receiving SIGHUP or SIGTERM a worker will await the currently running task forever.
On SIGINT, this value represents the time before the worker will attempt to kill the subprocess.
This time is only accurate to one worker heartbeat corresponding to `WORKER_TTL / 3`.

Defaults to `600` seconds.

### TASK\_PROTECTION\_TIME, TMPFILE\_PROTECTION\_TIME and UPLOAD\_PROTECTION\_TIME

Pulp uses `tasks`, `pulp temporary files` and `uploads` to pass data from the api to worker tasks.
These options allow to specify a timeinterval in minutes used for cleaning up stale entries.
If set to `0`, automatic cleanup is disabled.

Each one defaults to `0`.

### UVLOOP\_ENABLED

Enable using the [uvloop] event loop in the content-app workers.
This is [recommended by aiohttp] for performance improvements.

The `uvloop` python package must be installed in the content-app's system.
That's available as an optional dependency for pulpcore: `pulpcore[uvloop]`.

### VULN\_REPORT\_TASK\_LIMITER

This number determines the amount of concurrent vulnerability report processes that can be spawned
at one time. Increasing this number will generally increase the speed of the task, but will also
consume more resources of the worker. Defaults to 10 concurrent processes.

### WORKER\_TTL

The number of seconds before a worker should be considered lost.

Defaults to `30` seconds.

### WORKING\_DIRECTORY

The directory used by workers to stage files temporarily.

It should have permissions of:

- mode: 750
- owner: pulp (the account that pulp runs under)
- group: pulp (the group of the account that pulp runs under)
- SELinux context: `system_u:object_r:pulpcore_var_lib_t:s0`

Defaults to `/var/lib/pulp/tmp/`.

!!! note
    It is recommended that `WORKING_DIRECTORY` and `MEDIA_ROOT`
    exist on the same storage volume for performance reasons.
    Files are commonly staged in the `WORKING_DIRECTORY` and
    validated before being moved to their permanent home in `MEDIA_ROOT`.


## Redis Settings

!!! note
    To enable usage of Redis the [CACHE\_ENABLED](#cache_enabled) option must be set to `True`.

Below are some common settings used for Redis configuration.

### REDIS\_HOST

The hostname for Redis.

### REDIS\_PASSWORD

The password for Redis.

### REDIS\_PORT

The port for Redis.

Additionally, the following Redis settings can be set in your Pulp config:

- `REDIS_DB`
- `REDIS_URL`


## Kafka Settings

!!! note
    Kafka integration functionality is in tech preview and may change based on user feedback.

See [librdkafka configuration documentation] for details on client configuration properties.

### KAFKA\_BOOTSTRAP\_SERVERS

`bootstrap.servers` value for the client.
Specifies endpoint(s) for the kafka client.
Kafka integration is disabled if unspecified.

### KAFKA\_PRODUCER\_POLL\_TIMEOUT

Timeout in seconds for the kafka producer polling thread's `poll` calls.

Defaults to `0.1`.

### KAFKA\_SASL\_MECHANISM

`sasl.mechanisms` value for the client (optional).
Specifies the authentication method used by the kafka broker.

### KAFKA\_SASL\_PASSWORD

`sasl.password` value for the client (optional).
Password for broker authentication.

### KAFKA\_SASL\_USERNAME

`sasl.username` value for the client (optional).
Username for broker authentication.

### KAFKA\_SECURITY\_PROTOCOL

`security.protocol` value for the client.
What protocol to use for communication with the broker.

Defaults to `plaintext` (unencrypted).

### KAFKA\_SSL\_CA\_PEM

`ssl.ca.pem` value for the client (optional).
Used to override the TLS truststore for broker connections.

### KAFKA\_TASKS\_STATUS\_PRODUCER\_SYNC\_ENABLED

Whether to synchronously send task status messages.
When `True`, the task message is sent synchronously, otherwise the sends happen asynchronously,
with a background thread periodically sending messages to the kafka server.

Defaults to `False`.

### KAFKA\_TASKS\_STATUS\_TOPIC

What kafka topic to emit notifications to when tasks start/stop.

Defaults to `pulpcore.tasking.status`.

[Database Encryption]: site:pulpcore/docs/admin/guides/configure-pulp/db-encryption
[django 4.2]: https://docs.djangoproject.com/en/4.2/ref/settings/#default-file-storage
[Django authentication documentation]: https://docs.djangoproject.com/en/4.2/topics/auth/customizing/#authentication-backends
[Django database settings]: https://docs.djangoproject.com/en/4.2/ref/settings/#databases
[Django documentation on logging]: https://docs.djangoproject.com/en/4.2/topics/logging/#configuring-logging
[django-guid settings documentation]: https://django-guid.readthedocs.io/en/latest/settings.html
[Django secret key]: https://docs.djangoproject.com/en/4.2/ref/settings/#secret-key
[Django setting]: https://docs.djangoproject.com/en/4.2/ref/settings/
[django-storages]: https://django-storages.readthedocs.io/en/latest/index.html
[Django warning at the end of this section in their docs]: https://docs.djangoproject.com/en/4.2/howto/auth-remote-user/#configuration
[Enabling Debug Logging]: site:pulpcore/docs/admin/guides/troubleshooting/#enabling-debug-logging
[librdkafka configuration documentation]: https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md
[on-demand and streaming limitations]: site:pulpcore/docs/user/learn/on-demand-downloading/#on-demand-and-streamed-limitations
[recommended by aiohttp]: https://docs.aiohttp.org/en/stable/third_party.html#approved-third-party-libraries
[task diagnostics documentation]: site:pulpcore/docs/dev/learn/tasks/diagnostics.md
[uvloop]: https://github.com/MagicStack/uvloop
[Webserver Auth with Reverse Proxy]: site:pulpcore/docs/admin/guides/auth/external/#webserver-auth-with-reverse-proxy
