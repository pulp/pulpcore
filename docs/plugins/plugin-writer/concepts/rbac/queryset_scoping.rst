.. _queryset_scoping:

Restricting Viewable Objects
============================

With limited object-level permissions on certain objects, its desirable to restrict the objects
shown to users. This effectively causes a Pulp system with many users to have each user see only
"their" permissions.

This feature is generally referred to as Queryset Scoping because it is applied as an additional
filter on the base Queryset of a ViewSet. This causes the permission filtering to work with other
filterings applied by a user.


.. _enabling_queryset_scoping:

Enabling QuerySet Scoping
-------------------------

The support for this is built into ``pulpcore.plugin.viewsets.NamedModelViewSet``, which is often
the base class for any model-based ViewSet if Pulp. Objects will only be shown to users have access
to a specific permission either at the model-level or object-level. Enable this on your ViewSet that
inherits from ``pulpcore.plugin.viewsets.NamedModelViewSet`` by having the ``permission_classes``
class attribute include a permission class that implements the ``scope_queryset`` interface, like
the default permission class ``AccessPolicyFromDB``. To enable queryset scoping for
``AccessPolicyFromDB``, add the field ``scoping_hooks`` with a list of scoping function dictionaries
to the ViewSet's ``DEFAULT_ACCESS_POLICY``.

``NamedModelViewset`` has a useful default scoping function: ``scope_required_permissions`` for
basic scoping from a list of permissions, see example below. Each scoping function will be combined
using the OR operation by default. If you wish to have the functions combined using AND add the
field and value ``"operation": "and"`` to the hook dictionary.

For example Tasks are restricted only to those users with the "core.view_task" permission like
this::

    TaskViewSet(NamedModelViewSet):
        ...
        DEFAULT_ACCESS_POLICY = {
        ...
            "scoping_hooks": [
                {
                    "function": "scope_required_permissions",
                    "parameters": "core.view_task",
                }
            ],
        ...
        }


.. _manually_implementing_queryset_scoping:

Manually Implementing QuerySet Scoping
--------------------------------------

If your ViewSet does not inherit from ``pulpcore.plugin.viewsets.NamedModelViewSet`` or you would
like more control over the QuerySet Scoping feature it can be added manually by adding a
``get_queryset`` method to your ViewSet which returns the filtered QuerySet.

To look up objects by permission easily from an existing QuerySet use the ``get_objects_for_user``
provided by pulpcore or django-guardian. Here's an example where all items are displayed accessible
via either of the permission frameworks:

NOTE: Doing this will prevent the user from disabling queryset scoping.
# I think this section should be removed from the docs

.. code-block:: python

    from pulpcore.plugin.util import get_objects_for_user

    class MyViewSet(rest_framework.viewsets.GenericViewSet):

        def get_queryset(self):
            qs = super().get_queryset()
            permission_name = "my.example_permission"
            return get_objects_for_user(self.request.user, permission_name, qs=qs)
