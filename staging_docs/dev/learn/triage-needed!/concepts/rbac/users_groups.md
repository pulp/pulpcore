

# Users and Groups

Users and Groups are always stored in the Django database. This is a requirement so that `Roles` and
`Permissions` can relate to them.

```{eval-rst}

:User: Provided by Django with the ``django.contrib.auth.models.User`` model.
:Group: Provided by Django with the ``django.contrib.auth.models.Group`` model.
```

Any role can be assigned to either users, groups, or both. This includes both Model-level and
Object-level role assignments. Direct permission assignments are not recommended and cannot be
operated on within the Pulp-API.
