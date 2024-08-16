# Permissions and Roles

The permissions system provides a way to assign permissions as part of roles to specific users and
groups of users. The models driving this data are `django.contrib.auth.models.Permission` and
`pulpcore.plugin.models.role.Role`. Each `Permission` has a name, describing it and can be
associated with one or more `Role`. Roles can be assigned to users or groups either on the
Model-Level, Domain-level (if domains are enabled), or Object-Level.



## Model Permissions

`Permissions` in Django are tied to models and usually map to certain
actions performed thereon. By default, each model receives four permissions:

- The “add” permission limits the user’s ability to view the “add” form and add an object.
- The “change” permission limits a user’s ability to view the change list, view the “change”
  form and change an object.
- The “delete” permission limits the ability to delete an object.
- The “view” permission limits the ability to view an object.

The Model permissions are created automatically by Django, and receive a name like:
`<app_name>.<action>_<model_name>`. For example to change file remote the permission is named
`file.change_fileremote`. You can view the Permissions on a system via the Django ORM with:
`Permission.objects.all()`. See the [Django Permissions Docs](https://docs.djangoproject.com/en/4.2/topics/auth/default/#permissions-and-authorization) for more information on working with
permissions.

Here's an example of the Permissions automatically created for the `FileRemote` model:

- `file.add_fileremote`
- `file.view_fileremote`
- `file.change_fileremote`
- `file.delete_fileremote`



## Defining Custom Permissions

Any model can define custom permissions, and Django will automatically make a migration to add it
for you. See the [Django Custom Permissions Documentation](https://docs.djangoproject.com/en/4.2/topics/auth/customizing/#custom-permissions) for more information on how to do that. In contrast
to `AccessPolicies` and `creation_hooks`, permissions can only be defined by the plugin writer.
As a rule of thumb, permissions should be the atomic building blocks for roles and each action that
can be performed on an object should have its own permission.



## Custom Permission for Repository Content Modification

The Repository subclass is one place where it's recommended to create a custom permission that
manages the ability to modify RepositoryVersions underneath a Repository. While the add, create,
view, and delete default permissions apply to the Repository itself, this new custom permission is
intended to be required for any operations that produce RepositoryVersions, e.g. `sync`,
`modify`, or `upload`.

Here's an example of adding a permission like this for `FileRepository`:

```python
class FileRepository(Repository):

    ...

    class Meta:
        ...
        permissions = (
            ('modify_repo_content', 'Modify Repository Content'),
        )
```

!!! note

    It is not necessary to "namespace" this `modify_repo_content` permission because by including
    it in the meta class of your Detail view, it will already be namespaced on the correct object.




## Roles

`Roles` are basically sets of `Permissions`, and in Pulp, users and groups should receive their
`Permissions` exclusively via role assignments. Typical roles are `owner` for an object with all
the permissions to view modify and delete the object, or `viewer` limited to see the object. To
scope the reach of the permissions in a role, these role are assigned to `Users` or `Groups`
either on the model-level, domain-level (if domains are enabled), or the object-level.

### Role Levels

Domain-Level
: When the domains feature is enabled, a role is associated to a user or group for
access to a specific model within the specific domain and only that domain. This allows you
to express concepts like "Hilde can administer all FileRemotes within Domain 'foo'".

Object-Level
: A role is associated to a user or group for access to a specific instance of a
specific model. This allows you to express concepts like "Hilde can administer
FileRemote(name='foo remote').

Certain roles may contain permissions that are only ever checked on the model(or domain)-level.
For example the `creator` role for a model that contains the models `add` permission.

In the case for `FileRemote`, the typical set of roles provided by the plugin looks like:

```python
LOCKED_ROLES = {
    "file.fileremote_creator": ["file.add_fileremote"],
    "file.fileremote_owner": [
        "file.view_fileremote",
        "file.change_fileremote",
        "file.delete_fileremote",
        "file.manage_roles_fileremote",
    ],
    "file.fileremote_viewer": ["file.view_fileremote"],
}
```

### Locked and User-Defined

Roles come in two flavors, locked and user-defined.

First there are so called locked roles that are
provided by plugins. Their name needs to be prefixed by the plugin `app_label` followed by a dot
(see the example above). They can be seen, but not modified via the api, and are kept up to date
with their definition in the plugin code. That way, plugins can ship default access policies that
rely on those roles.

The other flavor is user defined roles. These are managed via the Pulp
API, and plugin code will not interfere with them. Users can opt to use the provided locked roles or
roll their own.
