# Enable and create Domains

!!! warning
    This feature requires plugin support to work correctly.

!!! warning
    This feature is provided as a tech preview and could change in backwards incompatible
    ways in the future.

## Overview

Domains are an optional feature that enables one sort of multi-tenancy in Pulp.
Enabling domains allows multiple tenants to use the same Pulp instance in a safe and isolated manner,
without worry that other users can modify or interfere with your workflows.
Each domain acts as a unique namespace for that user and their Pulp objects, completely isolated from the other domains.
To this end each domain can be customized to use their own storage backend to store their artifacts and content,
ensuring each user has complete control over the content they manage in Pulp.

Domains are meant for Pulp admins that need more multi-tenancy abilities than are provided through current RBAC features.
Domains help greatly when multiple, but distinctly separate tenants are sharing the same Pulp instance without having to resort to creating multiple Pulp instances.
See [RBAC Overview] for Pulp's RBAC capabilities if you are unsure what Pulp's RBAC can currently do.
However domains are not necessarily a replacement for RBAC.

## Enabling Domains

Domains are off by default and can be enabled by setting `DOMAIN_ENABLED = True` in your settings file and restarting Pulp.
In order to enable domains, each installed plugin needs to be domain compatible.
If an installed plugin is not compatible Pulp will fail to start.
See list below for current list of plugins with domain compatibility.
Once domains are enabled all current objects in Pulp will be found under the `default` domain.

!!! warning
    Before turning on domains in an existing system, you should completely drain the task queue of all running or waiting tasks.

## Creating Domains

Domains have three important fields:
a unique `name`, the backend `storage class` and the `storage settings` for the storage backend.
See [Storage] documentation to see available storage backends and settings.
The domain name must be unique and is used in the URL path after the `API_ROOT`, e.g. `/pulp/my_domain_name/api/v3/`.
You can also customize the content app behavior for your domain through the fields `redirect_to_object_storage` and `hide_guarded_distributions`.
See [settings] for more details on these.

```bash
pulp domain create \
  --name <domain_name> \
  --storage-class <storage_class> \
  --storage-settings <storage_settings>
```

Specific examples for different storage backends:

=== "FileSystem"
    ```bash
    pulp domain create \
      --name foo \
      --description foo \
      --storage-class pulpcore.app.models.storage.FileSystem \
      --storage-settings "{\"MEDIA_ROOT\": \"/var/lib/pulp/media/\"}"
    ```

=== "S3"
    ```bash
    pulp domain create \
      --name mydomain \
      --storage-class storages.backends.s3boto3.S3Boto3Storage \
      --storage-settings "{\"access_key\": \"AcVDppUlVkA6\", \"secret_key\": \"SFviCmMfRT6N\", \"bucket_name\": \"my-unique-bucket-name\", \"region_name\": \"us-east-1\", \"default_acl\": \"private\"}"
    ```

!!! note
    `default`, `content`, and `api` are reserved names that can not be used during creation or update.
    The `default` domain can not be updated or deleted.


!!! note
    To delete a domain all objects within that domain must be deleted first,
    including artifacts and orphaned content.


!!! note
    The AWS access key must be authorized to perform the `s3:ListBucket` and `s3:PutObject` operations.


!!! warning
    Changing the `storage-class` or `storage-settings` of an in-use domain is dangerous and can result in a broken domain.
    TODO Migration feature

## Using Domains

Once domains are enabled all URLs in Pulp will require the domain name in the path after the `API_ROOT` for the Pulp API,
e.g. `/pulp/my_domain_name/api/v3/`, or after the `CONTENT_PATH_PREFIX` for the Content App, e.g. `/pulp/content/my_domain_name/`.
Objects present in Pulp before enabling domains will now be present under the `default` domain.
To work in a domain you must specify the domain's name in the URL.

```bash
# List repositories in 'test' domain
pulp --domain test repository list

# Create a File Repository 'foo' in 'foo' domain
pulp --domain foo file repository create --name foo

# Create a File Repository 'foo' in 'boo' domain (Possible because of separate domains)
pulp --domain boo file repository create --name foo

# See Exposed Distributions in 'default' domain
pulp distribution list
```

Domains are isolated from each other and perform their own deduplication and uniqueness checks within their domain.
Therefore multiple domains can each have their own repository named 'foo';
a capability not available without domains as repository names were unique within a Pulp system, but are now unique within a domain.
This also means that content and artifact deduplication is no longer system wide, but instead performed at the domain level.
Since domains can each have their own unique storage backend, duplicate content across domains could be stored in multiple locations.
Also for separating tenants, it would be inappropriate to try to deduplicate across domains.

Most all Pulp objects and operations work the same within their domain.
Uploading, syncing, publishing, and distributing workflows are all supported with domains.
Objects are scoped to their domain and will not appear in other domains even if you have permissions on those domains.
Plugins that support RBAC will now also have access to a new permission level on the domain.
Assigning a role at the domain-level will allow users to operate with those permissions only within that domain.
Current global(model)-level roles should be converted to domain-level if you wish for the user to not have permission across all domains.

```bash
# Delete the global-level role
pulp user role-assignment remove --username <username> --role <role_name> --object ""

# Assign the role at the domain-level
pulp user role-assignment add --username <username> --role <role_name> --domain <domain_href>
```

!!! note
    Operations on resources across separate domains is not allowed.
    e.g. You can not add content from one domain to the repository of another domain even if you own both domains.


!!! warning
    Pulp Export and Import are currently not supported with domains enabled.


There are notable objects in Pulp like `Roles`, `Users`, and `Groups`, that are not a part of domains and remain global across the system.
These objects are closely intertwined with the RBAC system and currently do not make sense to be unique on the domain level.
Objects that are not a part of a domain are readable from any domain (with the correct permissions),
but are only operable on within the `default` domain, i.e. `Roles` can be read from any domain, but can only be created from the `default` domain.

[RBAC Overview]: site:pulpcore/docs/dev/learn/rbac/
[settings]: site:pulpcore/docs/admin/reference/settings/
[Storage]: site:pulpcore/docs/admin/guides/configure-pulp/configure-storages/
