

# Adding Automatic Permissions for New Objects

When creating new objects in either viewsets or tasks it's important to have the right permissions.
It is important that the permissions new objects receive work with the AccessPolicy so that newly
created objects can be authorized by the AccessPolicy as expected. The AccessPolicy statements are
user-configurable and so the permissions to be created for new objects are too. Similar to the
requirements for the AccessPolicy `statements`, plugin writers can define and ship a default
behavior for permissions on new objects, and then users can modify them as needed after migrations
are run.



## Defining New Object Permission Behaviors

The `AccessPolicy.creation_hooks` attribute defines a set of callables that are intended to be
run when new objects are created. These do not run automatically; your models should use the
`pulpcore.plugin.models.AutoAddObjPermsMixin` on the model as described in the
`enabling_new_object_permission_creation` section.

The `AccessPolicy.creation_hooks` attribute is optional because not all AccessPolicy objects
create objects. If no objects are created by an endpoint, there does not need to be a
`creation_hooks` attribute.

Permissions are associated to users via roles.

The most common auto-assignment of roles is to the creator of an object themselves. Here is an
example assigning the `"core.task_owner"` role to the creator of an object:

```python
{
    "function": "add_roles_for_object_creator",
    "parameters": {"roles": ["core.task_owner"]},
}
```

Another common auto-assignment of roles is to assign to one or more users explicitly. Here is an
example assigning the `"core.task_owner"` role to the users `["alice", "bob"]`.

```python
{
    "function": "add_roles_for_users",
    "parameters": {
        "roles": "core.task_owner",
        "users": ["alice", "bob"],
    },
}
```

A third common auto-assignment of roles is to assign to one or more groups explicitly. Here is an
example assigning the `"core.task_viewer"` role to the group `"foo"`.

```python
{
    "function": "add_roles_for_groups",
    "parameters": {
        "roles": ["core.task_viewer"],
        "groups": "foo",
    },
}
```

!!! note
All the hooks shipped with pulpcore accept either a single item or list of items for their
arguments like `roles`, `users` or `groups`.




## Enabling New Object Permission Creation

To enable automatic permission creation for an object managed by an AccessPolicy, have your model
use the `pulpcore.plugin.models.AutoAddObjPermsMixin`. See the example below as an example:

```python
class MyModel(BaseModel, AutoAddObjPermsMixin):
   ...
```

See the docstring below for more information on this mixin.

```{eval-rst}
.. autoclass:: pulpcore.app.models.access_policy.AutoAddObjPermsMixin

```



## Shipping a Default New Object Policy

In general, the default recommended is to use the `add_roles_for_object_creator` to assign the
view, change, and delete permissions for the object created. Here is an example of a default policy
like this:

```python
DEFAULT_ACCESS_POLICY = {
    "statements": <...>
    "creation_hooks": [
        {
            "function": "add_roles_for_object_creator",
            "parameters": {"roles": "file.fileremote_owner"},
        }
    ],
}
LOCKED_ROLES = {
    "file.fileremote_owner": [
        "file.view_fileremote", "file.change_fileremote", "file.delete_fileremote"
    ],
}
```

This effectively creates a "user isolation" policy which aligns with the examples from
`shipping_default_access_policy`.



## Defining Custom New Object Permission Callables

Plugin writers can use more than the built-in callables such as `add_roles_for_object_creator` or
`add_roles_for_users` by defining additional methods on the model itself. The callables defined in
the `function` are method names on the Model that need to be registered with
`REGISTERED_CREATION_HOOKS`:

```python
class MyModel(BaseModel, AutoAddObjPermsMixin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.REGISTERED_CREATION_HOOKS["my_custom_callable"] = self.my_custom_callable

    def my_custom_callable(self, role, users, groups):
        from pulpcore.app.util import assign_role
        for user in users:
            assign_role(role, user, self)  # self is the object being assigned
        for group in groups:
            assign_role(role, group, self)  # self is the object being assigned
```

This would be callable with a configuration like this one:

```python
{
    "function": "my_custom_callable",
    "parameters": {
        "role": "pulpcore.task_viewer",
        "users": ["bob"],
        "groups": [],
    },
}
```

!!! note
The `parameters` dict must actually match the creation hooks signature.

