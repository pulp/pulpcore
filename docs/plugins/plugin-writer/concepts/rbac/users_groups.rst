.. _users_and_groups:

Users and Groups
================

Users and Groups is always stored in the Django database. This is a requirement so that
``Roles`` or ``Permissions`` can relate to them.

:User: Provided by Django with the ``django.contrib.auth.models.User`` model.
:Group: Provided by Django with the ``django.contrib.auth.models.Group`` model.

Any role or permission can be assigned to either users, groups, or both. This includes both
Model-level and Object-level roles as well as permissions.
