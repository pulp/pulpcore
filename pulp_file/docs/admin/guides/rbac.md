# Role Based Access Control

Role based access control in Pulp File is configured using access policies for the following
`viewset_names`:

- `acs/file/file`
- `content/file/files`
- `distributions/file/file`
- `publications/file/file`
- `remotes/file/file`
- `repositories/file/file`
- `repositories/file/file/versions`

This document describes the default access policies shipped with Pulp File. Each of the above
policies can be modified to achieve a different RBAC behavior. Use the Pulp CLI to follow along
with the examples here.

!!! note
    This feature is currently in tech preview and is subject to change in future releases.


!!! note
    Customizing the access policy will cause any future changes to the default policies, like
    statement changes and bugfixes, to be ignored unless reset to the default policy.


## Default Roles

Pulp File ships with three default roles baked into each viewset, except for File Content and File
Repository Versions, that can be assigned to users for simple RBAC needs. The three roles for each
viewset are Creator, Viewer, and Owner. Roles can be assigned at the model or object level for each
user and group. Roles at the model will give the user/group permissions across all objects the role
covers. Roles at the object level will restrict the permissions to a particular instance of the
object.

### Creator Role

The Creator role contains just the `add` permission for that viewset's object, e.g. File
Repository's Creator role:

=== "Show Creator Role"

    ```bash
    pulp role show --name "file.filerepository_creator"
    ```

=== "Output"

    ```json
    {
        "pulp_href": "/pulp/api/v3/roles/ee3d368e-46da-430a-97bc-fbd5d207ebf3/",
        "pulp_created": "2022-03-23T21:13:24.183866Z",
        "name": "file.filerepository_creator",
        "description": null,
        "permissions": [
            "file.add_filerepository"
        ],
        "locked": true
    }
    ```

Only users with the `add` permission can create objects for that viewset. This role should always
be used as a model level role as it makes no sense for it to be assigned at the object level. Some
viewset actions will also require the user to have additional permissions for related parameters
on the object's creation. An example would be needing to have the `view` permission for remotes
attached to a repository:

```json
"statements": [
    ...
    {
      "action": [
        "create"
      ],
      "effect": "allow",
      "condition": [
        "has_model_perms:file.add_filerepository",
        "has_remote_param_model_or_obj_perms:file.view_fileremote"
      ],
      "principal": "authenticated"
    },
    ...
],
```

### Viewer Role

The Viewer role contains just the `view` permission for that viewset's object, e.g. File Remote's
Viewer role:

=== "Show Viewer Role"

    ```bash
    pulp role show --name "file.fileremote_viewer"
    ```

=== "Output"

    ```json
    {
        "pulp_href": "/pulp/api/v3/roles/d3bedaa3-4ffc-46d2-b4a5-6bc205f060dd/",
        "pulp_created": "2022-03-23T21:13:24.176520Z",
        "name": "file.fileremote_viewer",
        "description": null,
        "permissions": [
            "file.view_fileremote"
        ],
        "locked": true
    }
    ```

Having the `view` permission allows the user to see and read the object when performing list and
show operations on the viewset. Pulp File performs queryset scoping on the viewsets based off this
permission, which limits the objects a user can see and interact with. Users that have this role
at the model level will be able to see all of the viewset's objects in Pulp. Assigning this role
only at the object level allows you to select what the user can see.

```bash
# Allow alice to see every File publication
pulp user role-assignment add --role "file.filepublication_viewer" --username "alice" --object ""
# Allow bob to see just the publication in $PUB_HREF
pulp user role-assignment add --role "file.filepublication_viewer" --username "bob" --object "$PUB_HREF"
# Alternative to previous command, allows for specifying multiple users & groups
pulp file publication role add --role "file.filepublication_viewer" --user "bob" --user "charlie" --group "fighters" --href "$PUB_HREF"
```

### Owner Role

The Owner role contains all of the permissions available for that viewset's objects besides the
`add` permission, e.g. File ACS's Owner role:

=== "Show Owner Role"

    ```bash
    pulp role show --name "file.filealternatecontentsource_owner"
    ```

=== "Output"

    ```json
    {
        "pulp_href": "/pulp/api/v3/roles/7e17ae48-8a9f-49c4-a248-83b397c6a5e6/",
        "pulp_created": "2022-03-23T21:13:24.087395Z",
        "name": "file.filealternatecontentsource_owner",
        "description": null,
        "permissions": [
            "file.change_filealternatecontentsource",
            "file.delete_filealternatecontentsource",
            "file.manage_roles_filealternatecontentsource",
            "file.refresh_filealternatecontentsource",
            "file.view_filealternatecontentsource"
        ],
        "locked": true
    }
    ```

Besides the permissions for Read, Update, and Delete actions, the Owner role has the `mange_roles`
permission that allows the user to call the viewset's `add_role` and `remove_role` endpoints
for easy management of roles around that viewset's object. The Owner role will also contain
permissions for any additional action that can be performed on that viewset, for example `sync`
and `modify` permissions for File Repository. Having this role at model level will allow a user
to perform any action on any of the viewset's objects. This role is added by default to a user,
at the object level, upon object creation.

=== "Create a remote and show the added role"

    ```bash
    # alice has creator role for File remote
    pulp --username "alice" file remote create --name "foo" --url "$FIXTURE_URL"
    # alice now has the owner role for the created remote
    pulp file remote role list --name "foo"
    ```
=== "Output"

    ```json
    {
        "roles": [
            {
                "role": "file.fileremote_owner",
                "users": [
                    "alice"
                ],
                "groups": []
            }
        ]
    }
    ```

### Content and RepositoryVersions Permissions

File Content and RepositoryVersions are unique as they do not have any default roles on their
viewsets. Content's access policy allows any authenticated user to create file content, however
they must specify the repository to upload to since viewing content is scoped by the repositories
the user has permission for. RepositoryVersions' access policy requires the user to have
permissions on the parent repository in order to perform actions on the repository version. Both
objects have CRD permissions in the database that can be assigned to users, but currently their
access policies do not use them for authorization.

## Creating New Roles

The default roles shipped in Pulp File are locked roles. This means they can not be edited or
deleted. If they are not sufficient for your RBAC use cases, you can create custom roles that can
be assigned to users and groups. The example below shows how to create a role allowing one to
view multiple objects:

```bash
pulp role create --name "super_viewer" \
    --permission "file.filealternatecontentsource_viewer" \
    --permission "file.filedistribution_viewer" \
    --permission "file.filepublication_viewer" \
    --permission "file.fileremote_viewer" \
    --permission "file.filerepository_viewer"

# Assign new role to alice
pulp user role-assignment add --username "alice" --role "super_viewer"
```

!!! note
    You can only assigned roles at the object level if the role contains a permission for that
    object.


## Editing File Access Policies

Each Pulp File access policy can be edited to be more or less lenient. They can also be customized
on role assignment upon object creation. By default each access policy will assign the default
Owner role upon object creation. See the example below for how to view the File Repository's access
policy and then update it to assign the new role:

```bash
# View File Repository's Access Policy
pulp access-policy show --viewset-name "repositories/file/file"

# Update File Repository's Creation Hooks
pulp access-policy update --href "$REPO_AP_HREF" \
    --creation-hooks '[{"function": "add_roles", "parameters": {"roles": "super_viewer"}}]'
```

!!! note
    Access polices can be reset to their default using the reset endpoint, e.g:
    `pulp access-policy reset --href "$REPO_AP_HREF"`


!!! note
    Admin users always bypass any authorization checks.

