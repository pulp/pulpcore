.. _defining_access_policy:

Defining an Access Policy
=========================

The Access Policy controls the authorization of a given request and is enforced at the
viewset-level. Access policies are based on the AccessPolicy from `drf-access-policy
<https://rsinger86.github.io/drf-access-policy/policy_logic/>`_ which uses `policy statements
described here <https://rsinger86.github.io/drf-access-policy/policy_logic/>`_.

Example Policy
--------------

Below is an example policy used by ``FileRemote``, with an explanation of its effect below that::

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
            "condition": "has_model_perms:file.add_fileremote",
        },
        {
            "action": ["retrieve"],
            "principal": "authenticated",
            "effect": "allow",
            "condition": "has_model_or_obj_perms:file.view_fileremote",
        },
        {
            "action": ["update", "partial_update"],
            "principal": "authenticated",
            "effect": "allow",
            "condition": "has_model_or_obj_perms:file.change_fileremote",
        },
        {
            "action": ["destroy"],
            "principal": "authenticated",
            "effect": "allow",
            "condition": "has_model_or_obj_perms:file.delete_fileremote",
        },
    ]

The above policy allows the following four cases, and denies all others by default. Overall this
creates a "user isolation policy" whereby users with the ``file.add_fileremote`` permission can
create ``FileRemote`` objects, and users can only read/modify/delete ``FileRemote`` objects they
created.

Here's a written explanation of the policy statements:

* ``list`` is allowed by any authenticated user. Although users are allowed to perform an operation
  what they can list will still be restricted to :ref:`only the objects that user can view
  <queryset_scoping>`.
* ``create`` is allowed by any authenticated user with the ``file.add_fileremote`` permission.
* ``retrieve`` (the detail view of an object) is allowed by an authenticated user who has the
  ``file.view_fileremote`` permission. Although users are allowed to perform an operation what they
  can list will still be restricted to :ref:`only the objects that user can view
  <queryset_scoping>`.
* ``update`` or ``partial_update`` is allowed by an authenticated user who has the
  ``file.change_fileremote`` permission.
* ``destroy`` is allowed by any authenticated user with the ``file.delete_fileremote`` permission.

These names correspond with the `default DRF viewset action names
<https://www.django-rest-framework.org/api-guide/viewsets/#viewset-actions>`_.


Authorization Conditions
------------------------

Each policy statement can contain `drf-access-policy conditions <https://rsinger86.github.io/
drf-access-policy/statement_elements/#condition>`_ which is useful for verifying a user has one or
more permissions. Pulp ships many built-in checks. See the :ref:`permission_checking_machinery`
documentation for more information on available checks.

When multiple conditions are present, **all** of them must return True for the request to be
authorized.

.. warning::

    The ``admin`` user created on installations prior to RBAC being enabled has
    ``is_superuser=True``. Django assumes a superuser has any model-level permission even without it
    being assigned. Additionally, django-guardian when checking object-level permissions defaults to
    assuming the same although it is configurable. Generally, superusers are expected to bypass
    authorization checks.


Custom ViewSet Actions
----------------------

The ``action`` part of a policy statement can reference `any custom action your viewset has
<https://www.django-rest-framework.org/api-guide/viewsets/#marking-extra-actions-for-routing>`_. For
example ``FileRepositoryViewSet`` has a ``sync`` custom action used by users to sync a given
``FileRepository``. Below is an example of the default policy used to guard that action::

    {
        "action": ["sync"],
        "principal": "authenticated",
        "effect": "allow",
        "condition": [
            "has_model_or_obj_perms:file.modify_repo_content",
            "has_remote_param_model_or_obj_perms:file.view_fileremote",
        ]
    }


.. _storing_access_policy_in_db:

Storing an Access Policy in the DB
----------------------------------

All access policies are stored in the database in the `pulpcore.plugin.models.AccessPolicy` model,
which stores the policy statements described above. Here is a look at the ``AccessPolicy`` model:

.. autoclass:: pulpcore.plugin.models.AccessPolicy
   :members: viewset_name, statements, permissions_assignment

By storing these in the database they are readable to users with a GET to
``/pulp/api/v3/access_policies/``. Additionally users can PUT/PATCH modify them at
``/pulp/api/v3/access_policies/:uuid/``. Users cannot modify create or delete an Access Policy in
the database because only plugin writers create them and their viewset code expects a specific
AccessPolicy instance to exist.


.. _shipping_default_access_policy:

Shipping a Default Access Policy
--------------------------------

To ship a default access policy, define a dictionary named ``DEFAULT_ACCESS_POLICY`` as a class
attribute on a subclass of ``NamedModelViewSet`` containing both ``statements`` and
``permissions_assignment``. The ``AccessPolicy`` instance will be then be created in the
``pulp_migrate`` signal handler.

Here's an example of code to define a default policy:

.. code-block:: python

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
                    "condition": "has_model_perms:file.add_fileremote",
                },
                {
                    "action": ["retrieve"],
                    "principal": "authenticated",
                    "effect": "allow",
                    "condition": "has_model_or_obj_perms:file.view_fileremote",
                },
                {
                    "action": ["update", "partial_update"],
                    "principal": "authenticated",
                    "effect": "allow",
                    "condition": "has_model_or_obj_perms:file.change_fileremote",
                },
                {
                    "action": ["destroy"],
                    "principal": "authenticated",
                    "effect": "allow",
                    "condition": "has_model_or_obj_perms:file.delete_fileremote",
                },
            ],

            "permissions_assignment": [
                {
                    "function": "add_for_object_creator",
                    "parameters": None,
                    "permissions": [
                        "file.view_fileremote", "file.change_fileremote", "file.delete_fileremote"
                    ]
                },
            ],
        }
        <...>

For an explanation of the ``permissions_assignment`` see the
:ref:`shipping_a_default_new_object_policy` documentation.


.. _handling_objects_created_prior_to_RBAC:

Handling Objects created prior to RBAC
--------------------------------------

Prior to RBAC being enabled, ``admin`` was the only user and they have ``is_superuser=True`` which
generally causes them to pass any permission check even without explicit permissions being assigned.


.. _viewset_enforcement:

Viewset Enforcement
-------------------

Protecting a viewset with your saved AccessPolicy is done by declaring a ``permission_classes``
class attribute on your ViewSet that points to ``pulpcore.plugin.access_policy.AccessPolicyFromDB``.

For example, here is the FileRemoteViewSet which enables authorization enforcement as follows:

.. code-block:: python

    from pulpcore.plugin.access_policy import AccessPolicyFromDB

    class FileRemoteViewSet(NamedModelViewSet):
        ...
        permission_classes = (AccessPolicyFromDB,)
        ...
