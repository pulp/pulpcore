

# Plugin Concepts

Like the Pulp Core itself, all Pulp Plugins are Django Applications, and could be created like any
other Django app with `pulpcore-manager startapp <your_plugin>`. However, instead of writing all
of the boilerplate yourself, it is recommended that you start your plugin by utilizing the [Plugin
Template](https://github.com/pulp/plugin_template).  This guide will assume that you have used
the plugin_template, but if you are interested in the details of what it provides you, please see
`plugin-django-application` for more information for how plugins are "discovered" and connected to
the `pulpcore` Django app. Additional information is given as inline comments in the template.

## Plugin API Usage

Plugin Applications interact with pulpcore with two high level interfaces, **subclassing** and
adding **tasks**.



## Subclassing

Pulp Core and each plugin utilize [Django](https://docs.djangoproject.com/) and the [Django Rest
Framework](https://www.django-rest-framework.org/). Each plugin provides
`subclassing-models`, `subclassing-serializers`, and `subclassing-viewsets`. For
each object that a plugin writer needs to make, the `pulpcore.plugin` API provides base classes.
These base classes handle most of the boilerplate code, resulting in CRUD for each object out of
the box.

```{toctree}
:maxdepth: 2

subclassing/models
subclassing/serializers
subclassing/viewsets
subclassing/import-export
subclassing/replication
subclassing/pull-through
```



## Master/Detail Models

Typically pulpcore wants to define a set of common fields on a Model; for example,
`pulpcore.plugin.models.Remote` defines fields like `url`, `username`, `password`, etc.
Plugin writers are able to also add plugin-specific fields through subclassing this object.
Conceptually this is easy, but two practical problems arise:

- With each subclass becoming its own table in the database, the common fields get duplicated on
  each of these tables.
- Migrations are now no longer on a single table, but N tables produced from subclassing.

To address these issues, pulpcore uses Django's [Multi-table inheritance support](https://docs.djangoproject.com/en/4.2/topics/db/models/#multi-table-inheritance) to create a pattern Pulp
developers call the "Master/Detail pattern". The model defining the common fields is called the
"Master model", and any subclass of a Master model is referred to as a "Detail model".

For example, pulpcore defines the [Remote](https://github.com/pulp/pulpcore/blob/b575e1338e04978755a0231905950659aeea4ea9/pulpcore/app/models/repository.py#L268) Master model. It
inherits from `MasterModel` which identifies it as a Master model, and defines many fields. Then
pulp_file defines the [FileRemote](https://github.com/pulp/pulp_file/blob/68cdbde4f7f9609d987ec4e6694810e6085288db/pulp_file/app/models.py#L46) which is a Detail model. The
Detail model defines a `TYPE` class attribute and is a subclass of a Master model.

Typically Master models are provided by pulpcore, and Detail models by plugins, but this is not
strictly required. Here is a list of the Master models pulpcore provides:

- `pulpcore.plugin.models.AlternateContentSource`
- `pulpcore.plugin.models.Content`
- `pulpcore.plugin.models.ContentGuard`
- `pulpcore.plugin.models.Distribution`
- `pulpcore.plugin.models.Exporter`
- `pulpcore.plugin.models.Importer`
- `pulpcore.plugin.models.Publication`
- `pulpcore.plugin.models.Remote`
- `pulpcore.plugin.models.Repository`

Here are some examples of usage from the Detail side:

```python
>>> my_file_remote = FileRemote.objects.get(name="some remote name")

>>> type(my_file_remote)  # We queried the detail type so we expect that type of instance
pulp_file.app.models.FileRemote

>>> my_file_remote.policy = "streamed"  # The detail object acts like it has all the attrs
>>> my_file_remote.save()  # Django's multi-table inheritance handles where to put things

>>> my_master_remote = my_file_remote.master  # the `master` attr gives you the master instance

>>> type(my_master_remote)  # Let's confirm this is the Master model type
pulpcore.app.models.repository.Remote
```

The Master table in psql gets a column named `pulp_type` which stores the app name joined with the
value of the class attribute on the Detail column using a period. So with `FileRemote` defining the
class attribute `TYPE = "file"` and the `pulp_file` Django app name being `"file"` we expect a
`pulp_type` of `"file.file"`.The Detail table in psql has a foreign key pointer used to join
against the Master table. This information can be helpful when you want to query from the Master
side:

```python
>>> items = Remote.objects.filter(pulp_type="file.file")  # Get the File Remotes in Master table
>>> my_master_remote = items[0]  # my_master_remote has no detail defined fields

>>> type(my_master_remote)  # Let's confirm this is the `master` instance
pulpcore.app.models.repository.Remote
```

A Master model instance can be transformed into its corresponding Detail model object using the
`cast()` method. See the example below for usage. Additionally, It is possible to create subclasses
of Detail models, and in that case, the `cast()` method will always derive the most recent
descendent. Consider the usage from below.

```python
>>> my_detail_remote = my_master_remote.cast()  # Let's cast the master to the detail instance
>>> type(my_detail_remote)
pulp_file.app.models.FileRemote  # Now it's a detail instance with both master and detail fields
```



## Validating Models

Pulp ensures validity of its database models by carefully crafted serializers.
So all instances where resources are created or updated, those serializers must be used.

To create a `MyModel` from a `data` dictionary, the `MyModelSerializer` can be used like:

```python
serializer = MyModelSerializer(data=data)
serializer.is_valid(raise_exception=True)
instance = serializer.create(serializer.validated_data)
```

In the stages pipeline, you want to instantiate the content units without saving them to database
right away. The `ContentSaver` stage will then persist the objects in the database. This can be
established by:

```python
# In MyPluginFirstStage::run
# <...>
serializer = MyModelSerializer(data=data)
serializer.is_valid(raise_exception=True)
d_content = DeclarativeContent(
    content=MyModel(**serializer.validated_data),
    d_artifacts=[d_artifact],
)
await self.put(d_content)
# <...>
```



## Tasks

Any action that can run for a long time should be an asynchronous task. Plugin writers do not need
to understand the internals of the pulpcore tasking system. Workers automatically execute tasks,
including the ones deployed by plugins.

**Worker and Tasks Directories**

In pulp each worker is assigned a unique working directory living in `/var/lib/pulp/tmp/`, and
each started task will have its own clean temporary subdirectory therein as its current working
directory. Those will automatically be cleaned up once the task is finished.

If a task needs to create more temporary directories, it is encouraged to use
`tempfile.TemporaryDirectory(dir=".")` from the python standard library to place them in the
tasks working directory. This can be necessary, if the amount of temporarily saved data is too much
to wait for the automatic cleanup at the end of the task processing or to avoid naming conflicts.

**Making Temporary Files Available to Tasks**

Sometimes, files must be brought forward from a ViewSet to an executing task. The files may or may
not end up being artifacts in the end. To tackle this, one should use `PulpTemporaryFile`.

```python
# Example 1 - Saving a temporary file:
temp_file = PulpTemporaryFile(file=my_file)
temp_file.save()

# Example 2 - Validating the digest and saving a temporary file:
temp_file = PulpTemporaryFile.init_and_validate(
    my_file, expected_digests={'md5': '912ec803b2ce49e4a541068d495ab570'}
)
temp_file.save()

# Example 3 - Creating an Artifact from the PulpTemporaryFile:
try:
    artifact = Artifact.from_pulp_temporary_file(temp_file)
except Exception:
    temp_file.delete()
```

When dealing with a clustered deployment, different pulp services are not guaranteed to share a
common filesystem (like /usr/share/pulp). `PulpTemporaryFile` is the alternative for creating
files with the same storage technology that the artifacts use. Therefore, the temporary files
are accessible by all pulp instances.

**Reservations**

The tasking system adds a concept called **reservations** which ensures that actions that act on the
same resources are not run at the same time. To ensure data correctness, any action that alters the
content of a repository (thus creating a new version) must be run asynchronously, locking on the
repository and any other models which cannot change during the action. For example, sync tasks must
be asynchronous and lock on the repository and the remote. Publish should lock on the repository
whose version is being published. Reservations can be shared (for read only access) and exclusive
(for modifying access).

**Deploying Tasks**

Tasks are usually deployed from Views or Viewsets, please see `kick-off-tasks`.

```{toctree}
:maxdepth: 2

tasks/add-remove
tasks/publish
```

**Immediate Tasks**

When dispatching a task, one can specify whether it is eligible to be run immediately in the same
process right away given the reservations can be satisfied (defaults to `False`), and whether it
is eligible to be deferred for workers to be picked up later (defaults to `True`).
In case a task was marked for immediate execution, but the reservations were not satisfied, it will
be left in the task queue or marked as canceled, depending on the `deferred` attribute.

!!! warning
A task marked for immediate execution will not be isolated in the `pulpcore-worker`, but may
be executed in the current api worker. This will not only delay the response to the http call,
but also the complete single threaded gunicorn process. To prevent degrading the whole Pulp
service, this is only ever allowed for tasks that guarantee to perform fast **and** without
blocking on external resources. E.g. simple attribute updates, deletes... A model with a lot of
dependants that cause cascaded deletes may not be suitable for immediate execution.


**Diagnostics**

```{toctree}
:maxdepth: 2

tasks/diagnostics
```

**Task Groups**

Sometimes, you may want to create many tasks to perform different parts of one larger piece of work,
but you need a simple means to track the progress of these many tasks. Task Groups serve this purpose
by providing details on the number of associated tasks in each possible state.
For more details, please see `kick-off-tasks`.

**GroupProgressReports**

GroupProgressReport can track progress of each task in that group. GroupProgressReport needs to be
created and associated to the TaskGroup. From within a task that belongs to the TaskGroup, the
GroupProgressReport needs to be updated.

```python
# Once a TaskGroup is created, plugin writers should create GroupProgressReport objects
# ahead, so tasks can find them and update the progress.
task_group = TaskGroup(description="Migration Sub-tasks")
task_group.save()
group_pr = GroupProgressReport(
    message="Repo migration",
    code="create.repo_version",
    total=1,
    done=0,
    task_group=task_group)
group_pr.save()
# When a task that will be executing certain work, which is part of a TaskGroup, it will look
# for the TaskGroup it belongs to and find appropriate progress report by its code and will
# update it accordingly.
task_group = TaskGroup.current()
progress_repo = task_group.group_progress_reports.filter(code='create.repo_version')
progress_repo.update(done=F('done') + 1)
# To avoid race conditions/cache invalidation issues, this pattern needs to be used so that
# operations are performed directly inside the database:

# .update(done=F('done') + 1)

# See: https://docs.djangoproject.com/en/4.2/ref/models/expressions/#f-expressions
# Important: F() objects assigned to model fields persist after saving the model instance and
# will be applied on each save(). Do not use save() and use update() instead, otherwise
# refresh_from_db() should be called after each save()
```

## Sync Pipeline

```{toctree}
:maxdepth: 2

sync_pipeline/sync_pipeline
```

## Domain Multi-tenancy

Pulp supports a namespacing feature called Domains that allows users to create their own Domain for
their objects to live in. This feature is optional and requires plugins to be domain compatible in
order to be enabled.

```{toctree}
:maxdepth: 2

domains/domains_compatibility
```



## Role Based Access Control

Pulp uses a policy-based approach for Role Based Access Control (RBAC).

Plugin writers can:

- Enable authorization for a viewset
- Ship a default access policy
- Express what default object-level and model-level permissions created for new objects
- Check permissions at various points in task code as needed

This allows users to then:

- Modify the default access policy on their installation for custom authorization
- Modify the default object-level and model-level permissions that are created for new objects

```{toctree}
:maxdepth: 2

rbac/overview
rbac/permissions
rbac/users_groups
rbac/access_policy
rbac/adding_automatic_permissions
rbac/queryset_scoping
```

## Content Protection

Users can configure a `ContentGuard` to protect a `Distribution` on their own, but some plugins
want to offer built-in content protection features. For example pulp_container may only want a user
to download container images they have rights to based on some permissions system pulp_container
could provide.

For more information, see the `ContentGuard Usage by Plugin Writers
<plugin-writers-use-content-protection>` documentation.

## Plugin Settings

Plugins can define settings by creating a `<your plugin>.app.settings` module containing settings
as you would define in the Django Settings File itself. `pulpcore` ships the actual settings.py
file so settings cannot be added directly as with most Django deployments. Instead as each plugin is
loaded, pulpcore looks for the `<your plugin>.app.settings` module and uses `dynaconf` to
overlay the settings on top of `pulpcore`'s settings and user provided settings.

Settings are parsed in the following order with later settings overwriting earlier ones:

1. Settings from `/etc/pulp/settings.py`.
2. Settings from `pulpcore.app.settings` (the pulpcore provided settings defaults).
3. Plugin settings from `<your plugin>.app.settings`.

In some cases, a setting should not overwrite an existing setting, but instead add to it. For
example, consider adding a custom log handler or logger to the [LOGGING](https://github.com/pulp/pulpcore/blob/ec336c2b7bc7cefd3a28fc69dcd1c65655332841/pulpcore/app/settings.py#L183-L202)
settings. You don't want to fully overwrite it, but instead add or overwrite only a sub-portion.
`dynaconf` provides the [dynaconf_merge feature](https://www.dynaconf.com/merging/) which is for merging settings instead of overwriting them. For
example, pulp_ansible makes use of this [here](https://github.com/pulp/pulp_ansible/blob/31dd6b77f0e2748644a4b76607be4a6cd2b6ce89/pulp_ansible/app/settings.py).

Some settings require validation to ensure the user has entered a valid value. Plugins can add
validation for their settings using validators added in a `dynaconf` hook file that will run
after all the settings have been loaded. Create a `<your plugin>.app.dynaconf_hooks` module like
below so `dynaconf` can run your plugin's validators. See [dynaconf validator docs](https://www.dynaconf.com/validation/) for more information on writing validators.

```python
from dynaconf import Validator

def post(settings):
    """This hook is called by dynaconf after the settings are completely loaded"""
    settings.validators.register(
        Validator(...),
        Validator(...),
        ...
    )
    settings.validators.validate()
```



## Custom API URL Routes

The [typical plugin viewsets](subclassing-viewsets) are all suburls under `/pulp/api/v3/`, but
some content types require additional urls outside of this area. For example pulp_ansible provides
the Galaxy API at `/pulp_ansible/galaxy/`.

Place a urls.py that defines a `urlpatterns` at the root of your Python package, and the pulpcore
plugin loading code will append those urls to the url root. This allows your urls.py to be a typical
Django file. For example pulp_ansible uses a [urls.py defined here](https://github.com/pulp/pulp_ansible/blob/master/pulp_ansible/app/urls.py)



## Custom Content App Routes

The Content App may also require custom routes, for example [pulp_container](https://github.com/pulp/pulp_container/blob/master/pulp_container/app/content.py) defines some. Read more about how
to `customize the content app with custom routes <content-app-docs>`.



## Configuring Reverse Proxy with Custom URLs

When a plugin requires either Pulp API or Pulp Content App custom urls, the reverse proxy, i.e.
either Nginx or Apache, need to receive extra configuration snippets to know which service to route
the custom URLs to.

A best practice is to document clearly the custom URL requirements your plugin needs. Environments
such as k8s, podman, or docker may need manual configuration. Having clear docs is a minimum.

You can ship webserver snippets as part of your Python package with three steps:

1\. Create a python package named `webserver_snippets` directory inside your app, e.g.
`pulp_ansible.app.webserver_snippets`. Like all Python packages it will have an `__init__.py`.

2. Create an `nginx.conf` and an `apache.conf`.

3\. Create an entry in MANIFEST.in to have the packaged plugin include the `apache.conf` and
`nginx.conf` files.

Here is an example in [pulp_ansible's webserver configs](https://github.com/pulp/pulp_ansible/tree/master/pulp_ansible/app/webserver_snippets).

For the `nginx.conf` you can use variables with the names `pulp-api` and `pulp-content` as the
location for the backend services. For example, to route the url `/pulp_ansible/galaxy/` to the
Pulp API you could have your `nginx.conf` contain:

```
location /pulp_ansible/galaxy/ {
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Host $http_host;
    # we don't want nginx trying to do something clever with
    # redirects, we set the Host: header above already.
    proxy_redirect off;
    proxy_pass http://pulp-api;
}
```

The Apache config provides variables containing the location of the Pulp Content App and the Pulp
API as `pulp-api` and `pulp-content` respectively. Below is an equivalent snippet to the one
above, only for Apache:

```
ProxyPass /pulp_ansible/galaxy http://${pulp-api}/pulp_ansible/galaxy
ProxyPassReverse /pulp_ansible/galaxy http://${pulp-api}/pulp_ansible/galaxy
```

For the MANIFEST.in entry, you'll likely want one like the example below which was taken from
[pulp_ansible's MANIFEST.in](https://github.com/pulp/pulp_ansible/blob/master/MANIFEST.in):

```
include pulp_ansible/app/webserver_snippets/*
```



## Overriding the Reverse Proxy Route Configuration

Sometimes a plugin may want to control the reverse proxy behavior of a URL at the webserver. For
example, perhaps an additional header may want to be set at the reverse proxy when those urls are
forwarded to the plugin's Django code. To accomplish this, the
`custom app route <custom-content-app-routes>` can be used when it specifies a more-specific
route than the pulp-oci-images base webserver configuration provides.

For example assume the header `FOO` should be set at the url `/pulp/api/v3/foo_route`. Below are
two examples of a snippet that could do this (one for Nginx and another for Apache).

Nginx example:

```
location /pulp/api/v3/foo_route {
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Host $http_host;

    proxy_set_header FOO 'asdf';  # This is the custom part

    # we don't want nginx trying to do something clever with
    # redirects, we set the Host: header above already.
    proxy_redirect off;
    proxy_pass http://pulp-api;
}
```

Apache example:

```
<Location "/pulp/api/v3/foo_route">
    ProxyPass /pulp/api http://${pulp-api}/pulp/api
    ProxyPassReverse /pulp/api http://${pulp-api}/pulp/api
    RequestHeader set FOO "asdf"
</Location>
```

These snippets work because both Nginx and Apache match on "more-specific" routes first regardless
of the order in the config file. The pulp-oci-env ships the a default of `/pulp/api/v3` so
anything containing another portion after `v3` such as `/pulp/api/v3/foo_route` would be more
specific.



## Plugin API Stability and Deprecation Policy

The `pulpcore.plugin` API can introduce breaking changes, and will be introduced in the following
way. For this example, assume that pulpcore 3.8 introduces a breaking change by changing the call
signature of a method named `def foo(a, b)` which is importable via the plugin API.

In 3.8 the following changes happen:

1. The new method would be introduced as a new named function `def the_new_foo(...)` or some
   similar name.

2. The existing method signature `def foo(a, b)` is left in-tact.

3. The `foo` method would have the a Python `DeprecationWarning` added to it such as:

   ```
   from pulpcore.app.loggers import deprecation_logger
   deprecation_logger.warning("foo() is deprecated and will be removed in pulpcore==3.9; use the_new_foo().")
   ```

4. A `CHANGES/plugin_api/XXXX.deprecation` changelog entry is created explaining how to port
   plugin code onto the new call interface.

Then in 3.9 the following happens:

1. The `def foo(a, b)` method is deleted entirely.
2. A `CHANGES/plugin_api/XXXX.removal` changelog entry is created explaining what has been
   removed.

!!! note
Deprecation log statements are shown to users of your plugin when using a deprecated call
interface. This is by design to raise general awareness that the code in-use will eventually be
removed.


This also applies to models importable from `pulpcore.plugin.models`. For example, an attribute
that is being renamed or removed would follow a similar deprecation process described above to allow
plugin code one release cycle to update their code compatibility.

Logging of deprecation warnings can be disabled by raising the log level for the
`pulpcore.deprecation` logger in the pulpcore settings file:

```
LOGGING = {
    # ...
    "loggers": {
        "pulpcore.deprecation": {
            "level": "ERROR",
    }
}
```



## Declaring Dependencies

Pulpcore and Pulp plugins are Python applications and are expected to follow Python ecosystem norms
including declaring direct dependencies using the setuptools `install_requires` keyword in your
`setup.py`.

Pulpcore and Pulp plugins are expected to do two things when declaring dependencies:

1\. Declare an upper bound to prevent a breaking-change release of a dependency from breaking user
installations. To prevent unexpected breakages due to new plugin releases, this typically is the
current latest release of a dependency (assuming a plugin is compatible with the latest release).
The latest release is preferred because it allows each new dependency release to be tested, and it
prevents unexpected user breakages when dependencies release breaking changes.

2\. Declare as broad a range of compatible versions as possible to minimize conflicts between your
code and other Python projects installed in the same Python environment.

Here are some examples assuming our code directly depends on the `jsonschema` library and assuming
the latest `jsonschema` release is 4.4.2:

`jsonschema>=2.3,<=4.4.2` - Assuming this is accurate, this is the best declaration because it
declares as broad an expression of compatibility as safely possible.

`jsonschema<=4.4.2` - This is appropriate if the appropriate lower bound is not known.

`jsonschema~=4.4` - This should be avoided. Use an upper and lower bound range instead.

`jsonschema==4.4.0` - This is a last resort and needs an exceptional reason to do so.

`jsonschema` - This doesn't declare an upper bound, so this won't work. The CI will fail this.

Any code that you import directly should have its dependency declared as a requirement. This
includes code that you also would receive as dependencies of dependencies. For example, all plugins
import and use Django directly, but pulpcore also includes Django. Since your plugin uses Django
directly, your plugin should declare its dependency on Django.

!!! note
Why add a requirement when pulpcore is known to provide it? To continue with the Django
example... Django can introduce breaking changes with each release, so if your plugin relies on
pulpcore to declare the Django requirement, and then pulpcore upgrades, your plugin could
receive breaking changes with a new version of pulpcore. These breaking changes could be subtle
and not be noticeable until they affect your users. By your plugin declaring the dependency on
Django directly, at install/upgrade time (in the CI), you'll know right away you have a
conflicting dependency on Django.


One useful tool for managing the upperbound is [dependabot](https://github.com/dependabot) which
can open PRs raising the upper bound when new releases occur. These changes will go through the CI
which allows your dependency upper bound raising to be tested.

The challenging part of maintaining the lower bound is that it is not tested due to `pip` in the
CI wanting to use the latest version. Here are a few examples of when you want to raise the lower
bound:

- A plugin code change uses a new dependency feature
- A bug in the lower bound version of a dependency affects your plugin's users and a fix is
  available in a newer version of the dependency.
- Plugin code is incompatible with the lower bound version of a dependency and the solution is to
  declare a new lower bound.



## Checksum Use In Plugins

The `ALLOWED_CONTENT_CHECKSUMS` setting provides the list of allowed checksums a Pulp installation
is allowed to handle. This includes two types of "checksum handling":

1. Generating checksums. Only hashers in the `ALLOWED_CONTENT_CHECKSUMS` list should be used for
   checksum generation.
2. Passing through checksum data to clients. Pulp installations should not deliver checksum data to
   clients that are not in the `ALLOWED_CONTENT_CHECKSUMS` list. For example, the RPM plugin
   publications contain checksums that Pulp does not generate, and it should restrict the checksum
   data used in those publications to the set of allowed hashers in `ALLOWED_CONTENT_CHECKSUMS`.

!!! note
The plugin API provides the `pulpcore.plugin.pulp_hashlib` module which provides the `new`
function. This is a wrapper around `hashlib.new` which raises an exception if a hasher is
requested that is not listed in the `ALLOWED_CONTENT_CHECKSUMS` setting. This is a convenience
facility allowing plugin writers to not check the `ALLOWED_CONTENT_CHECKSUMS` setting
themselves.


(il8n-expectations)=

## Internationalization Expectations

pulpcore and its plugins are expected to internationalize all user-facing strings using Python's
gettext facilities. This allows Pulp to be translated to other languages and be more usable for a
broader base of users.

Administrator facing strings are expected *not* to be internationalized. These include all log
statements, migration output print statements, django management commands, etc. These not being
internationalized will remain in English. This expectation was formed after feedback from
multi-language speakers who believe having error messages for admins in English would reduce the
time to finding a fix and was generally less surprising.



## Zero-Downtime Upgrades

Eventually, Pulp users will be able to upgrade without first stopping Pulp services. This has been
[requested from the community](https://discourse.pulpproject.org/t/support-zero-downtime-updates/645),
To work towards that goal, developers of `pulpcore` or a plugin should follow these requirements:

- Migrations must not break earlier versions code still running during an upgrade.
- Task code must be backwards compatible until the next major Pulp version.

Future user upgrades will likely run as follow:

1. Run the migrations while old pulp code is online. Old code, is using the new data format.
2. Rolling restart old code to become new code. Old and new code is running at the same time!

# Zero-Downtime Migrations

The significant challenge with online migrations is that the db state the migration applies has to
work with both newer and older versions of Pulp code. For example, consider a model field that is to
be renamed. After renaming the field, Django would generate a migration that renames the specified
column. This would break all previous code which expects the previous column name.

Before getting into specific suggestions, the general pattern is to do the following:

1. The migration should be split into two parts: a "compatible with earlier code migration" and a
   "breaking earlier code migration". In continuing the column rename example, it would become a
   "create a new column" migration, and later a "delete the original column" migration.
2. The "breaking earlier code migration" should be delivered in a later release. It contains the
   the component versions that would not be broken by that change. When that migration goes to run
   it uses the db info in the db for each running pulp process to determine if any components are
   running a version that would break if this change is applied.

The solution to this will be highly dependant on the details of the migration, but here are some
likely patterns to be applied:

1. Avoid it. Is this rename really that important? Is it worth the trouble?
2. Rename the model attributes in code, but leave the actual column name as-is with
   the [db_column](https://docs.djangoproject.com/en/4.2/ref/models/fields/#db-column).
3. Have an "old" and a "new" column and use database triggers to keep data written to one to also be
   written to the other and vice-versa.

Here's an example:

pulp_file wants to rename a model attribute `old` to be called `new` in the next pulp_file
release, let's say that's pulp_file 1.10.0. Let's assume that avoiding the rename altogether or
using the `db-column` option to just rename it in the ORM are not viable.

This could be done as follows:

- Add the `new` field next to the `old` field and have Django auto-create a migration adding
  `new`.
- The same migration needs to install a new trigger that anytime `old` is written to, `new` is
  also written to and vice-versa. For example, something [like this](https://www.appsloveworld.com/postgresql/100/94/how-to-dual-write-to-two-columns-in-one-table-using-postgres-trigger)
  This allows the new code to read/write exclusively with `new` and the old code to deal with `old`.
- Write a data migration that updates the `new` column with `old` data in batches. Use batching
  to avoid a long table-lock.
- Have the codebase of pulp_file 1.10.0 stop using `old` entirely.

At a later time, e.g. pulp_file 1.13.0, a migration will be shipped to remove column `old`. That
migration needs to do two things things:

- Prior to running ensure via the database records that there are no pulp components running with
  pulp_file \< 1.10.0. If there are, abort running the migration and notify the user they need to
  upgrade to a version pulp_file>=1.10,\<1.13.0.
- Remove the database trigger and then the column `old`.

# Data Migrations

One problem that can arise from data migrations is the use of table-locks which would prevent other
code still running from executing concurrently. The typical solution is to have data migrations
operate in transactional batches which avoids a table-lock and instead creates row-locks.

# Tasking System

Tasking also has some considerations to allow code upgrades; specifically, tasks dispatched from
older codebases could run on newer, upgraded workers. To ensure this always works tasks must be
forever backwards compatible until the next major Pulp version. For example, you cannot have a
breaking signature change in tasking code and if this is needed you need to make a new task name and
preserve the old code until the next major Pulp version.

!!! note
Users not performing zero downtime upgrades who are still wary of any task incompatibilities,
should consider running the pulpcore worker in burst mode (`pulpcore-worker --burst`) after
shutting down all the api and content workers to drain the task queue.

