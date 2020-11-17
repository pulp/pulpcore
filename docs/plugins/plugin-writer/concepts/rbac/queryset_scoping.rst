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
inherits from ``pulpcore.plugin.viewsets.NamedModelViewSet`` by setting the
``queryset_filtering_required_permission`` class attribute to the value of the permission name.

For example Tasks are restricted only to those users with the "core.view_task" permission like
this::

    TaskViewSet(NamedModelViewSet):
        ...
        queryset_filtering_required_permission = "core.view_task"


.. _manually_implementing_queryset_scoping:

Manually Implementing QuerySet Scoping
--------------------------------------

If your ViewSet does not inherit from ``pulpcore.plugin.viewsets.NamedModelViewSet`` or you would
like more control over the QuerySet Scoping feature it can be added manually by adding a
``get_queryset`` method to your ViewSet which returns the filtered QuerySet.

To look up objects by permission easily from an existing QuerySet use the ``klass`` argument to
the ``get_objects_for_user`` provided by django-guardian. Here's an example:

.. code-block:: python

    from guardian.shortcuts import get_objects_for_user

    class MyViewSet(rest_framework.viewsets.GenericViewSet):

        def get_queryset(self):
            qs = super().get_queryset()
            permission_name = "my.example_permission"
            return get_objects_for_user(self.request.user, permission_name, klass=qs)
