# Restricting Viewable Objects

With limited object-level permissions on certain objects, its desirable to restrict the objects
shown to users. This effectively causes a Pulp system with many users to have each user see only
"their" permissions.

This feature is generally referred to as Queryset Scoping because it is applied as an additional
filter on the base Queryset of a ViewSet. This causes the permission filtering to work with other
filterings applied by a user.

!!! note

    If Domains are enabled, querysets will be scoped by the current request's domain before being
    passed onto RBAC queryset scoping.




## Enabling QuerySet Scoping

The support for this is built into `pulpcore.plugin.viewsets.NamedModelViewSet`, which is often
the base class for any model-based ViewSet if Pulp. Queryset Scoping is performed by the ViewSet's
`get_queryset` method which calls each permission class' method `scope_queryset` if present.
Pulp's default permission class, `pulpcore.app.AccessPolicyFromDB`, implementation of
`scope_queryset` calls the ViewSet function in the AccessPolicy field `queryset_scoping` if
defined. This field can be changed by the user to any method on the ViewSet or set empty if they
wish to turn off Queryset Scoping for that view:

```python
DEFAULT_ACCESS_POLICY = {
    ...
    # Call method `scope_queryset` on ViewSet to perform Queryset Scoping
    "queryset_scoping": {"function": "scope_queryset"},
    ...
}
```

`NamedModelViewSet` has a default `scope_queryset` implementation that will scope the query
based of the `queryset_filtering_required_permission` class attribute set on ViewSet.
Objects will only be shown to users that have access to this specific permission either at the
model-level or object-level.

For example Tasks are restricted only to those users with the "core.view_task" permission like
this:

```python
TaskViewSet(NamedModelViewSet):
    ...
    queryset_filtering_required_permission = "core.view_task"
```



## Manually Implementing QuerySet Scoping

Default scoping behavior can be overriden by supplying your own `scope_queryset` method.
`scope_queryset` takes one argument, the queryset to be scoped, and returns the scoped queryset.
Content ViewSet's have their `scope_queryset` method overriden to scope based on repositories
the user can see.

!!! note

    When queryset scoping is enabled for content you must also use the
    `has_required_repo_perms_on_upload` access condition on the upload endpoint to ensure users
    specify a repository for upload or they won't be able to see their uploaded content.


Extra Queryset Scoping methods can be defined on the ViewSet to allow users to choose different
behaviors besides On/Off. The method must accept the queryset as the first argument. Additional
parameters can also be accepted by supplying them in a `parameters` section of the
`queryset_scoping` field of the AccessPolicy like so:

```python
from pulpcore.plugin.viewsets import NamedModelViewSet
from pulpcore.plugin.util import get_objects_for_user

class MyViewSet(NamedModelViewSet):

    DEFAULT_ACCESS_POLICY = {
        # Statements omitted
        "queryset_scoping" : {
            # This entire field is editable by the user
            "function": "different_permission_scope",
            "parameters": {"permission": "my.example_permission"}
        }
    }

    def different_permission_scope(qs, permission):
        """Example extra scoping method that uses a user specified permission to scope."""
        return get_objects_for_user(self.request.user, permission, qs=qs)
```

If your ViewSet does not inherit from `pulpcore.plugin.viewsets.NamedModelViewSet` or you would
like more control over the QuerySet Scoping feature it can be added manually by adding a
`get_queryset` method to your ViewSet which returns the filtered QuerySet.

To look up objects by permission easily from an existing QuerySet use the `get_objects_for_user`
provided by pulpcore. Here's an example:

```python
from pulpcore.plugin.util import get_objects_for_user

class MyViewSet(rest_framework.viewsets.GenericViewSet):

    def get_queryset(self):
        qs = super().get_queryset()
        permission_name = "my.example_permission"
        return get_objects_for_user(self.request.user, permission_name, qs=qs)
```

!!! warning

    If you have custom ViewSets and plan to add Domains compatibility to your plugin, you must
    scope your objects by the domain in the ViewSet's `get_queryset` method to comply
    with Domain's isolation policies.

