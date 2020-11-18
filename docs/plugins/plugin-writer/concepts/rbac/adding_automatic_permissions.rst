.. _adding_automatic_permissions_for_new_objects:

Adding Automatic Permissions for New Objects
============================================

When creating new objects in either viewsets or tasks it's important to have the right permissions.
It is important that the permissions new objects receive work with the AccessPolicy so that newly
created objects can be authorized by the AccessPolicy as expected. The AccessPolicy statements are
user-configurable and so the permissions to be created for new objects are too. Similar to the
requirements for the AccessPolicy ``statements``, plugin writers can define and ship a default
behavior for permissions on new objects, and then users can modify them as needed after migrations
are run.


.. _defining_new_object_permission_behaviors:

Defining New Object Permission Behaviors
----------------------------------------

The ``AccessPolicy.permissions_assignment`` attribute defines a set of callables that are intended
to be run when new objects are created. These do not run automatically; your models should use the
``pulpcore.plugin.models.AutoAddObjPermsMixin`` on the model as described in the
:ref:`enabling_new_object_permission_creation` section.

The ``AccessPolicy.permissions_assignment`` attribute is optional because not all AccessPolicy
objects create objects. If no objects are created by an endpoint, there does not need to be a
``permissions_assignment`` attribute.

The most common auto-assignment of permissions is to the creator of an object themselves. Here is an
example assigning the ``["pulpcore.view_task", "pulpcore.change_task", "pulpcore.delete_task"]``
permissions to the creator of an object:

.. code-block:: python

    {
        "function": "add_for_object_creator",
        "parameters": null,
        "permissions": ["pulpcore.view_task", "pulpcore.change_task", "pulpcore.delete_task"]
	}

Another common auto-assignment of permissions is to assign to one or more users explicitly. Here is
an example assigning the ``["pulpcore.view_task", "pulpcore.change_task", "pulpcore.delete_task"]``
permissions to the users ``["alice", "bob"]``.

.. code-block:: python

    {
        "function": "add_for_users",
        "parameters": ["alice", "bob"],
        "permissions": ["pulpcore.view_task", "pulpcore.change_task", "pulpcore.delete_task"]
    }

A third common auto-assignment of permissions is to assign to one or more groups explicitly. Here is
an example assigning the ``"pulpcore.view_task"`` permission to the group ``"foo"``.

.. code-block:: python

    {
        "function": "add_for_groups",
        "parameters": "foo",
        "permissions": "pulpcore.view_task"
    }

.. note::

    Both the ``add_for_users`` and ``add_for_groups`` accept either a single item or list of items
    for both the ``parameters`` and ``permissions`` attributes.


.. _enabling_new_object_permission_creation:

Enabling New Object Permission Creation
---------------------------------------

To enable automatic permission creation for an object managed by an AccessPolicy, have your model
use the ``pulpcore.plugin.models.AutoAddObjPermsMixin``. See the example below as an example:

.. code-block:: python


    class MyModel(BaseModel, AutoAddObjPermsMixin):
       ACCESS_POLICY_VIEWSET_NAME = "mymodel"
       ...

See the docstring below for more information on this mixin.

.. autoclass:: pulpcore.app.models.access_policy.AutoAddObjPermsMixin


.. _shipping_a_default_new_object_policy:

Shipping a Default New Object Policy
------------------------------------

In general, the default recommended is to use the ``add_for_object_creator`` to assign the view,
change, and delete permissions for the object created. Here is an example of a default policy like
this:

.. code-block:: python

    FILE_REMOTE_PERMISSIONS_ASSIGNMENT = [
        {
            "function": "add_for_object_creator",
            "parameters": None,
            "permissions": [
                "file.change_fileremote", "file.change_fileremote", "file.delete_fileremote"
            ]
        }
    ]

    AccessPolicy.objects.create(
        viewset_name="remotes/file/file",
        statements=FILE_REMOTE_STATEMENTS,
        permissions_assignment=FILE_REMOTE_PERMISSIONS_ASSIGNMENT
    )

This effectively creates a "user isolation" policy which aligns with the examples from
:ref:`shipping_default_access_policy`.


.. _defining_custom_new_object_permission_callables:

Defining Custom New Object Permission Callables
-----------------------------------------------

Plugin writers can use more than the built-in callables such as ``add_for_object_creator`` or
``add_for_users`` by defining additional methods on the model itself. The callables defined in the
``function`` are method names on the Model with the following signature:

.. code-block:: python

    class MyModel(BaseModel, AutoAddObjPermsMixin):

        def my_custom_callable(self, permissions, parameters):
            # NOTE: permissions and parameters can be either a single entity or a list of entities
            from guardian.shortcuts import assign_perm
            user_or_group = parameters
            for permission in permissions:
                assign_perm(permissions, user_or_group, self)  # self is the object being assigned

This would be callable with a configuration like this one:

.. code-block:: python

    {
        "function": "my_custom_callable",
        "parameters": "asdf",
        "permissions": "pulpcore.view_task"
    }


.. _auto_removing_permissions_on_object_deletion:

Auto Removing Permissions On Object Deletion
--------------------------------------------

A mixin is provided for use on your models to automatically delete all object-level permissions when
an object is deleted. This is provided by the ``pulpcore.plugin.models.AutoDeleteObjPermsMixin``
mixin.

.. code-block:: python


    class MyModel(BaseModel, AutoDeleteObjPermsMixin):
       ...

See the docstring below for more information on this mixin.

.. autoclass:: pulpcore.app.models.access_policy.AutoDeleteObjPermsMixin
