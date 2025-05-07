# Overview

The goals of the authorization system are to:

- Make Pulp safe as a multi-user system
- Rely on User and Group definitions in the Django database, but allow them to come from anywhere
- Enforce permission checks at each viewset using a policy based approach
- Give users fine-grained control over each viewset's policy

## Architecture

Pulp's authorization model has the following architecture:

![RBAC Architecture](site:pulpcore/docs/assets/images/rbac_architecture.png)

Task Permissions Check:
: A permission check that occurs inside of Task code. This tends to use
permission checking calls like `has_perm` or `has_perms`
[provided by Django](https://docs.djangoproject.com/en/4.2/ref/contrib/auth/#django.contrib.auth.models.User.has_perm).

Permission Checking Machinery
: A set of methods which can check various conditions such as if a
requesting user has a given permission, or is a member of a group that has a given permission,
etc. See the [permission_checking_machinery](site:pulpcore/docs/dev/learn/rbac/permissions/) section for the complete list of available
methods.

Users and Groups
: Users and Groups live in the Django database and are used by the Permission Checking Machinery.
See the [users_and_groups](site:pulpcore/docs/dev/learn/rbac/users_groups/) documentation for more information.

## Getting Started

To add authorization for a given resource, e.g. `FileRemote`, you'll need to:

**Define the Policy:**

1. Define the default `statements` of the new Access Policy for the resource. See the
    `defining_access_policy` documentation for more information on that.
1. Define the `roles` as sets of permissions for that resource.
1. Define the default role associations created for new objects using the `creation_hooks`
    attribute of the new Access Policy for the resource. See the
    [Adding Automatic Permissions](site:pulpcore/docs/dev/learn/rbac/adding_automatic_permissions/)
    documentation for more information on that.
1. Ship that Access Policy as the class attribute `DEFAULT_ACCESS_POLICY` of a
    `NamedModelViewSet`. This will contain the `statements` and `creation_hooks` attributes.
    Ship the roles as the `LOCKED_ROLES` attribute accordingly. See the
    `shipping_default_access_policy` documentation for more information on this.
1. Add the `RolesMixin` to the viewset and add statements for managing roles to the access
    policy. Usually this is accompanied by adding a `manage_roles` permission on the model.

**Enforce the Policy:**

1. `pulpcore.plugin.access_policy.AccessPolicyFromDB` is configured as the default permission
    class, so by specifying a `DEFAULT_ACCESS_POLICY` it will automatically be enforced. See the
    `viewset_enforcement` docs for more information on this.

**Add QuerySet Scoping:**

1. Define a `queryset_filtering_required_permission` attribute on your viewset that names the
    permissions users must have to view an object. This is possible if your viewset is a subclass of
    the `pulpcore.plugin.models.NamedModelViewSet`. See the `enabling_queryset_scoping`
    documentation for more information.
