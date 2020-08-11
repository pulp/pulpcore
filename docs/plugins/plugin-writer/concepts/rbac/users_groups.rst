.. _users_and_groups:

Users and Groups
================

Users and Groups is always stored in the Django database. This is a requirement so that
``Permissions`` can relate to them.

:User: Provided by Django with the ``django.contrib.auth.models.User`` model.
:Group: Provided by Django with the ``django.contrib.auth.models.Group`` model.

Any permission can be assigned to either users, groups, or both. This includes both Model-level and
Object-level permissions.


.. _viewing_users_and_groups_via_UI:

Viewing Users and Groups via a UI
---------------------------------

The built-in django-admin site located at ``/admin/`` provides views into User, Group, and group
membership data.

.. note::

    Any user attempting to access the django-admin site will need to have their ``is_staff`` user
    attribute set to ``True``. The built-in ``admin`` user will have ``is_staff=True`` by default.


.. _model_level_permissions_via_UI:

Model-level Permissions via a UI
--------------------------------

The django-admin site also provides views into the Permissions that Users and Groups have.
Additionally you can add and remove Permissions here as well.

Model-level permissions are not associated with a specific instance so they can be managed on the
User or Group page itself. Object-level permissions are associated with specific instances, so those
can be managed on the django-admin page corresponding with the object itself.


.. _enabling_object_views_in_django_admin:

Enabling Object Views in django-admin
-------------------------------------

The `django-admin site <https://docs.djangoproject.com/en/2.2/ref/contrib/admin/>`_ by default does
not show objects until the plugin writer has specifically enabled them. Giving users the ability to
manage object-level permissions is the primary reason to enable an object in django-admin instead of
allowing API-only access or the DRF browseable interface for viewing Pulp data.

``django-guardian`` provides the `GuardedModelAdmin <https://django-guardian.readthedocs.io/en/
latest/api/guardian.admin.html#guardedmodeladmin>`_ and `GuardedModelAdminMixin <https://
django-guardian.readthedocs.io/en/latest/api/guardian.admin.html#guardedmodeladminmixin>`_ objects
which provide the ability to manage object-level permissions for objects. Use those when enabling
your object in django-admin to provide users with the ability to manage object-level permissions.

.. warning::

    django-admin objects need to be read-only except for the object-level permissions themselves.
    This is because Pulp uses DRF serializers for data validation and django-admin bypasses that.

    It's recommended to declare `readonly_fields <https://docs.djangoproject.com/en/2.2/ref/contrib
    /admin/#django.contrib.admin.ModelAdmin.readonly_fields>`_ with all model field names to ensure
    the data is readable but not editable.


.. _object_level_permissions_via_UI:

Object-level Permissions via a UI
---------------------------------

If plugin writers have enabled the object in the djano-admin site as described above, users can
view, add, and remove object-level permissions in the django-admin site as well.

When viewing a specific object instance, e.g. a specific ``Task`` or ``FileRemote`` instance in
django-admin, an icon on the top-right will say ``OBJECT PERMISSIONS``. Clicking this will take the
user to a page where object-level permissions can be viewed, added, changed, and deleted. If this
link is missing, ensure you've enabled the Task as a subclass of ``GuardedModelAdmin``.
