

# Defining an Access Policy

The Access Policy controls the authorization of a given request and is enforced at the
viewset-level. Access policies are based on the AccessPolicy from [drf-access-policy](https://rsinger86.github.io/drf-access-policy/policy_logic/) which uses [policy statements
described here](https://rsinger86.github.io/drf-access-policy/policy_logic/).

## Example Policy

Below is an example policy used by `FileRemote`, with an explanation of its effect below that:

```
[
    {
        "action": ["list"],
        "principal": "authenticated",
        "effect": "allow",
    },
    {
        "action": ["create"],
        "principal": "authenticated",
        "effect": "allow",
        "condition": "has_model_or_domain_perms:file.add_fileremote",
    },
    {
        "action": ["retrieve"],
        "principal": "authenticated",
        "effect": "allow",
        "condition": "has_model_or_domain_or_obj_perms:file.view_fileremote",
    },
    {
        "action": ["update", "partial_update", "set_label", "unset_label"],
        "principal": "authenticated",
        "effect": "allow",
        "condition": "has_model_or_domain_or_obj_perms:file.change_fileremote",
    },
    {
        "action": ["destroy"],
        "principal": "authenticated",
        "effect": "allow",
        "condition": "has_model_or_domain_or_obj_perms:file.delete_fileremote",
    },
]
```

The above policy allows the following four cases, and denies all others by default. Overall this
creates a "user isolation policy" whereby users with the `file.add_fileremote` permission can
create `FileRemote` objects, and users can only read/modify/delete `FileRemote` objects they
created.

Here's a written explanation of the policy statements:

- `list` is allowed by any authenticated user. Although users are allowed to perform an operation
  what they can list will still be restricted to `only the objects that user can view
  <queryset_scoping>`.
- `create` is allowed by any authenticated user with the `file.add_fileremote` permission.
- `retrieve` (the detail view of an object) is allowed by an authenticated user who has the
  `file.view_fileremote` permission. Although users are allowed to perform an operation what they
  can list will still be restricted to `only the objects that user can view
  <queryset_scoping>`.
- `update` or `partial_update` is allowed by an authenticated user who has the
  `file.change_fileremote` permission.
- `destroy` is allowed by any authenticated user with the `file.delete_fileremote` permission.

These names correspond with the [default DRF viewset action names](https://www.django-rest-framework.org/api-guide/viewsets/#viewset-actions).

## Authorization Conditions

Each policy statement can contain [drf-access-policy conditions](https://rsinger86.github.io/drf-access-policy/statement_elements/#condition) which is useful for verifying a user has one or
more permissions. Pulp ships many built-in checks. See the `permission_checking_machinery`
documentation for more information on available checks.

When multiple conditions are present, **all** of them must return True for the request to be
authorized.

!!! note
If you are making your plugin compatible with Domains, then use the `has_model_or_domain_perms`
and `has_model_or_domain_or_obj_perms` checks where appropriate.


!!! warning
The `admin` user created on installations prior to RBAC being enabled has
`is_superuser=True`. Django assumes a superuser has any model-level permission even without it
being assigned. Django's permission checking machinery assumes superusers bypass authorization
checks.


## Custom ViewSet Actions

The `action` part of a policy statement can reference [any custom action your viewset has](https://www.django-rest-framework.org/api-guide/viewsets/#marking-extra-actions-for-routing).
For example `FileRepositoryViewSet` has a `sync` custom action used by users to sync a given
`FileRepository`. Below is an example of the default policy used to guard that action:

```
{
    "action": ["sync"],
    "principal": "authenticated",
    "effect": "allow",
    "condition": [
        "has_model_or_domain_or_obj_perms:file.modify_repo_content",
        "has_remote_param_model_or_domain_or_obj_perms:file.view_fileremote",
    ]
}
```



## Storing an Access Policy in the DB

All access policies are stored in the database in the `pulpcore.plugin.models.AccessPolicy` model,
which stores the policy statements described above. Here is a look at the `AccessPolicy` model:

```{eval-rst}
.. autoclass:: pulpcore.plugin.models.AccessPolicy
   :members: viewset_name, statements, creation_hooks
```

By storing these in the database they are readable to users with a GET to
`/pulp/api/v3/access_policies/`. Additionally users can PUT/PATCH modify them at
`/pulp/api/v3/access_policies/:uuid/`. Users cannot modify create or delete an Access Policy in
the database because only plugin writers create them and their viewset code expects a specific
AccessPolicy instance to exist.



## Shipping a Default Access Policy

To ship a default access policy, define a dictionary named `DEFAULT_ACCESS_POLICY` as a class
attribute on a subclass of `NamedModelViewSet` containing all of `statements` and
`creation_hooks`. The `AccessPolicy` instance will then be created in the `pulp_migrate`
signal handler. In the same way you might want to specify a `LOCKED_ROLES` dictionary that will
define roles as lists of permissions to be used in the access policy.

Here's an example of code to define a default policy:

```python
class FileRemoteViewSet(RemoteViewSet):

<...>
    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_perms:file.add_fileremote",
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:file.view_fileremote",
            },
            {
                "action": ["update", "partial_update", "set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:file.change_fileremote",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:file.delete_fileremote",
            },
        ],

        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {
                    "roles": "file.fileremote_owner",
                },
            },
        ],
    }
    LOCKED_ROLES = {
        "file.fileremote_owner": [
            "file.view_fileremote", "file.change_fileremote", "file.delete_fileremote"
        ],
        "file.fileremote_viewer": ["file.view_fileremote"],
    }
    <...>
```

For an explanation of the `creation_hooks` see the
`shipping_a_default_new_object_policy` documentation.

The attribute `LOCKED_ROLES` contains roles that are managed by the plugin author. Their name
needs to be prefixed by the plugins `app_label` with a dot to prevent collisions. Roles defined
there will be replicated and updated in the database after every migration. They are also marked
`locked=True` to prevent being modified by users. The primary purpose of these roles is to allow
plugin writers to refer to them in the default access policy.



## Allow Granting Permissions by the Object Owners

To allow object owners to grant access to other users, first add a `manage_roles` permission to
the model.

```python
class FileRemote(Remote):
    <...>

    class Meta:
        permissions = [
            ("manage_roles_fileremote", "Can manage roles on file remotes"),
        ]
```

Now include the `RolesMixin` in the definition of the viewset and add statements for its verbs.

```python
class FileRemoteViewSet(RemoteViewSet, RolesMixin):
    <...>

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            <...>
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_domain_or_obj_perms:file.manage_roles_fileremote"],
            },
        ]
    }

    LOCKED_ROLES = {
        "file.fileremote_owner": [
            <...>
        <...>
    }
```



## Handling Objects created prior to RBAC

Prior to RBAC being enabled, `admin` was the only user and they have `is_superuser=True` which
generally causes them to pass any permission check even without explicit permissions being assigned.



## Viewset Enforcement

Pulp configures the `DEFAULT_PERMISSION_CLASSES` in the settings file to use
`pulpcore.plugin.access_policy.AccessPolicyFromDB` by default. This ensures that by defining a
`DEFAULT_ACCESS_POLICY` on your Viewset, Pulp will automatically save it to the database at
migration-time, and your Viewset will be protected without additional effort.

This strategy allows users to completely customize or disable the DRF Permission checks Pulp uses
like any typical DRF project would.

Also like a typical DRF project, individual Viewsets or views can also be customized to use a
different Permission check by declaring the `permission_classes` check. For example, here is the
`StatusView` which disables permission checks entirely as follows:

```python
class StatusView(APIView):
    ...
    permission_classes = tuple()
    ...
```



## Permission Checking Machinery

drf-access-policy provides a feature to enable conditional checks to be globally available as their
docs [describe here](https://rsinger86.github.io/drf-access-policy/reusable_conditions/). Pulp
enables the `reusable_conditions` in its settings.py file, allowing a variety of condition checks
to be globally available. Pulp enables this as follows:

```python
DRF_ACCESS_POLICY = {"reusable_conditions": ["pulpcore.app.global_access_conditions"]}
```

The `pulpcore.app.global_access_conditions` provides the following checks that are available for
both users and plugin writers to use in their policies:

```{eval-rst}
.. automodule:: pulpcore.app.global_access_conditions
   :members:

```



## Custom Permission Checks

Plugins can provide their own permission checks by defining them in a
`app.global_access_conditions` module and adding an operation like

```python
DRF_ACCESS_POLICY = {
    "dynaconf_merge_unique": True,
    "reusable_conditions": ["pulp_container.app.global_access_conditions"],
}
```

to their `app.settings` module.
