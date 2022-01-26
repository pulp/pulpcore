Overview
========

The goals of the authorization system are to:

* Make Pulp safe as a multi-user system
* Rely on User and Group definitions in the Django database, but allow them to come from anywhere
* Enforce permission checks at each viewset using a policy based approach
* Give users fine-grained control over each viewset's policy

Architecture
------------

Pulp's authorization model has the following architecture:

.. image:: /static/rbac_architecture.png
    :align: center

:Request Authorization: Each request is authorized by a `drf-access-policy <https://rsinger86.
    github.io/drf-access-policy/>`_ based policy at the viewset-level. You can learn more about
    defining an access policy :ref:`here <defining_access_policy>`.

:Task Permissions Check: A permission check that occurs inside of Task code. This tends to use
    permission checking calls like `has_perm` or `has_perms` `provided by Django <https://
    docs.djangoproject.com/en/2.2/ref/contrib/auth/#django.contrib.auth.models.User.has_perm>`_.

:Permission Checking Machinery: A set of methods which can check various conditions such as if a
    requesting user has a given permission, or is a member of a group that has a given permission,
    etc. See the :ref:`permission_checking_machinery` section for the complete list of available
    methods.

:Users and Groups: Users and Groups live in the Django database and are used by the Permission
    Checking Machinery. See the :ref:`users_and_groups` documentation for more information.


Getting Started
---------------

To add authorization for a given resource, e.g. ``FileRemote``, you'll need to:

**Define the Policy:**

1. Define the default ``statements`` of the new Access Policy for the resource. See the
   :ref:`defining_access_policy` documentation for more information on that.
2. Define the ``roles`` as sets of permissions for that resource.
3. Define the default role associations created for new objects using the ``creation_hooks``
   attribute of the new Access Policy for the resource. See the
   :ref:`adding_automatic_permissions_for_new_objects` documentation for more information on that.
4. Define the permissions used for QuerySet scoping through the ``filtering_permissions`` attribute
   of the new Access Policy for the resource. See the :ref:`enabling_queryset_scoping`
   documentation for more information.
5. Ship that Access Policy as the class attribute ``DEFAULT_ACCESS_POLICY`` of a
   ``NamedModelViewSet``. This will contain the ``statements``, ``creation_hooks`` and
   ``filtering_permissions`` attributes.
   Ship the roles as the ``LOCKED_ROLES`` attribute accordingly. See the
   :ref:`shipping_default_access_policy` documentation for more information on this.

**Enforce the Policy:**

1. ``pulpcore.plugin.access_policy.AccessPolicyFromDB`` is configured as the default permission
   class, so by specifying a ``DEFAULT_ACCESS_POLICY`` it will automatically be enforced. See the
   :ref:`viewset_enforcement` docs for more information on this.
