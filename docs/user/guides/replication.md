# Replicate from an Upstream Pulp

!!! warning
    This feature requires plugin support to work correctly.

!!! warning
    This feature is provided as a tech preview and could change in backwards incompatible
    ways in the future.

## Overview

Replication allows a Pulp instance to mirror repositories and distributions from another
("upstream") Pulp server. When replication runs, Pulp discovers the distributions available on the
upstream server and automatically creates the corresponding remotes, repositories, and distributions
locally. Content is then synced so that the local instance serves the same content as the upstream.

Each subsequent replication run is idempotent: objects that already exist are updated only when
necessary, new upstream distributions are added, and distributions that no longer exist upstream are
cleaned up according to the configured policy.

!!! note
    Replicate can also be used to copy content from one domain to another within a Pulp instance!

## Creating an Upstream Pulp

To replicate from an upstream server you first register it as an **Upstream Pulp** object. At a
minimum you need a name and the base URL of the upstream server.

```bash
pulp upstream-pulp create \
    --name "my-upstream" \
    --base-url "https://upstream.example.com" \
    --username "admin" \
    --password "password"
```

### Configuration Fields

| Field | Description |
|-------|-------------|
| `name` | A unique name for this upstream server. |
| `base_url` | The transport, hostname, and optional port of the upstream Pulp (e.g. `https://upstream.example.com`). |
| `api_root` | The API root path. Defaults to `pulp`. |
| `domain` | The domain on the upstream Pulp to replicate from, if the upstream has domains enabled. |
| `username` / `password` | Credentials for authenticating with the upstream Pulp API. |
| `ca_cert` | A PEM-encoded CA certificate used to validate the upstream server's TLS certificate. |
| `client_cert` / `client_key` | PEM-encoded client certificate and private key for mutual TLS authentication. |
| `tls_validation` | Whether to verify the upstream server's TLS certificate. Defaults to `True`. |
| `q_select` | A filter expression to select which upstream distributions to replicate. See [Filtering Distributions](#filtering-distributions-with-q_select). |
| `policy` | Controls how replication manages local objects. One of `all`, `labeled`, or `nodelete`. See [Replication Policies](#replication-policies). Defaults to `all`. |

## Running Replication

Trigger a replication by running:

```bash
pulp upstream-pulp replicate --upstream-pulp "my-upstream"
```

This dispatches an asynchronous task group. Each upstream distribution results in individual tasks
for creating/updating remotes, repositories, distributions, and syncing content. You can monitor the
task group to track overall progress.

On a successful replication, the `last_replication` timestamp on the Upstream Pulp object is updated.

## Filtering Distributions with q_select

By default, replication mirrors all distributions from the upstream server. Use the `q_select` field
to filter which distributions are replicated. The filter syntax supports the same `q` filter
expressions available on the distributions list endpoint.

### Basic Label Filtering

Select distributions that have a specific label:

```bash
pulp upstream-pulp update \
    --upstream-pulp "my-upstream" \
    --q-select "pulp_label_select='production'"
```

Select distributions with a specific label key and value:

```bash
pulp upstream-pulp update \
    --upstream-pulp "my-upstream" \
    --q-select "pulp_label_select='env=staging'"
```

### Complex Expressions

Combine filters with `AND`, `OR`, and `NOT` operators:

```bash
# Replicate distributions labeled 'team=alpha' OR 'team=beta'
pulp upstream-pulp update \
    --upstream-pulp "my-upstream" \
    --q-select "pulp_label_select='team=alpha' OR pulp_label_select='team=beta'"

# Replicate odd-labeled distributions but exclude a specific one
pulp upstream-pulp update \
    --upstream-pulp "my-upstream" \
    --q-select "pulp_label_select='odd' AND NOT pulp_label_select='upstream=7'"
```

When replication runs with a `q_select` filter, only the matching upstream distributions are
replicated. Distributions that were previously replicated but no longer match the filter are removed
(subject to the configured [policy](#replication-policies)).

To clear the filter and replicate all distributions again:

```bash
pulp upstream-pulp update --upstream-pulp "my-upstream" --q-select ""
```

## Replication Policies

The `policy` field controls how replication handles local objects, particularly when upstream
distributions are removed or no longer match a `q_select` filter.

### `all` (default)

Replication manages **all** local objects within the domain that match the replicated content types.
When an upstream distribution disappears, the corresponding local distribution, repository, and
remote are deleted -- even if they were created manually and not by a previous replication.

### `labeled`

Replication only manages objects that it created in a previous run. Objects created by replication
are tagged with an `UpstreamPulp` label linking them to the specific Upstream Pulp object. Manually
created local objects with the same content types are left untouched, even if they share names with
upstream distributions. If a replicated object has its `UpstreamPulp` label removed, replication
will no longer manage or delete it.

### `nodelete`

Replication creates and updates objects but **never deletes** any local objects, regardless of
whether they were created by replication or manually.

```bash
# Set the policy on an existing upstream
pulp upstream-pulp update --upstream-pulp "my-upstream" --policy "labeled"
```

## Sync Optimization

Replication automatically skips syncing repositories when no content changes have occurred on the
upstream since the last successful replication. This is determined by comparing the
`last_replication` timestamp with the upstream distribution's `no_content_change_since` timestamp.

A sync will still be triggered if:

- It is the first replication (no `last_replication` timestamp exists).
- The Upstream Pulp configuration was modified after the last replication.
- The upstream distribution's content has changed since the last replication.

## Roles and Permissions

Replication uses Pulp's RBAC system. The following built-in roles are available for Upstream Pulp
objects:

| Role | Permissions |
|------|-------------|
| `core.upstreampulp_creator` | Can create new Upstream Pulp objects. |
| `core.upstreampulp_owner` | Full control: view, change, delete, replicate, and manage roles. Automatically assigned to the creator. |
| `core.upstreampulp_viewer` | Can view Upstream Pulp objects. |
| `core.upstreampulp_user` | Can view and trigger replication, but cannot modify the Upstream Pulp configuration. |
