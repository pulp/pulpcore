Permissions
===========

The permissions system provides a way to assign permissions to specific users and groups of users.
The model driving this data is provided by ``django.contrib.auth.models.Permission``. Each
``Permission`` has a name, describing it and can be associated with one or more users or groups.

Two types of permissions exist: Model-Level and Object-Level.

:Model-Level: A permission that is associated with a specific model, but not an instance of that
              model. This allows you to express concepts like "Hilde can modify all FileRemotes".
:Object-Level: A permission that is associated with a specific instance of a specific model. This
               allows you to express concepts like "Hilde can modify FileRemote(name='foo remote').


.. _model_level_permissions:

Model-Level Permissions
-----------------------

By default, each model receives four permissions:

* The “add” permission limits the user’s ability to view the “add” form and add an object.
* The “change” permission limits a user’s ability to view the change list, view the “change” form and change an object.
* The “delete” permission limits the ability to delete an object.
* The “view” permission limits the ability to view an object.

The Model-level permissions are created automatically by Django, and receive a name like:
``<app_name>.<action>_<model_name>``. For example to change file remote the permission is named
``file.change_fileremote``. You can view the Permissions on a system via the Django ORM with:
``Permission.objects.all()``. See the `Django Permissions Docs <https://docs.djangoproject.com/en/
2.2/topics/auth/default/#permissions-and-authorization>`_ for more information on working with
permissions.

Here's an example of the Permissions automatically created for the ``FileRemote`` model:

* ``file.add_fileremote``
* ``file.view_fileremote``
* ``file.change_fileremote``
* ``file.delete_fileremote``


.. _object_level_permissions:

Object-Level Permissions
------------------------

Object-level permissions are provided by `django-guardian <https://django-guardian.readthedocs.io/
en/stable/>`_ which is a dependency of Pulp and enabled by default. This extends the normal Django
calls `has_perm(perm, obj=None) <https://docs.djangoproject.com/en/2.2/ref/contrib/auth/
#django.contrib.auth.models.User.has_perm>`_ `has_perms(perm_list, obj=None <https://docs.
djangoproject.com/en/2.2/ref/contrib/auth/#django.contrib.auth.models.User.has_perms>`_ to give
meaning to the ``obj`` portion of the call which Django otherwise would ignore.

Django-guardian has great docs on what it provides for interacting with object-level permissions:

* `Assigning object permissions <https://django-guardian.readthedocs.io/en/latest/userguide/assign.html#assign-obj-perms>`_
* `Checking object permissions <https://django-guardian.readthedocs.io/en/latest/userguide/check.html#standard-way>`_
* `Removing object permissions <https://django-guardian.readthedocs.io/en/latest/userguide/remove.html>`_
* `Helpful shortcut functions <https://django-guardian.readthedocs.io/en/latest/api/guardian.shortcuts.html>`_


.. _defining_custom_permissions:

Defining Custom Permissions
---------------------------

Any model can define a custom permission, and Django will automatically make a migration to add it
for you. See the `Django Custom Permissions Documentation <https://docs.djangoproject.com/en/2.2/
topics/auth/customizing/#custom-permissions>`_ for more information on how to do that.


.. _custom_permission_for_repository_content_modification:

Custom Permission for Repository Content Modification
-----------------------------------------------------

The Repository subclass is one place where it's recommended to create a custom permission that
manages the ability to modify RepositoryVersions underneath a Repository. While the add, create,
view, and delete default permissions apply to the Repository itself, this new custom permission
is intended to be required for any operations that produce RepositoryVersions, e.g. ``sync``,
``modify``, or ``upload``.

Here's an example of adding a permission like this for ``FileRepository``:

.. code-block:: python

    class FileRepository(Repository):

        ...

        class Meta:
            ...
                permissions = (
            ('modify_repo_content', 'Modify Repository Content'),
            )

.. note::

    It is not necessary to "namespace" this ``modify_repo_content`` permission because by including
    it in the meta class of your Detail view, it will already be namespaced on the correct object.

.. _permission_checking_machinery:

Permission Checking Machinery
-----------------------------

drf-access-policy provides a feature to enable conditional checks to be globalls available as their
docs `describe here <https://rsinger86.github.io/ drf-access-policy/reusable_conditions/>`_. Pulp
enables the ``reusable_conditions`` in its settings.py file, allowing a variety of condition
checks to be globally available. Pulp enables this as follows:

.. code-block:: python

    DRF_ACCESS_POLICY = {"reusable_conditions": "pulpcore.app.global_access_conditions"}

The ``pulpcore.app.global_access_conditions`` provides the following checks that are available for
both users and plugin writers to use in their policies:

.. automodule:: pulpcore.app.global_access_conditions
   :members:
