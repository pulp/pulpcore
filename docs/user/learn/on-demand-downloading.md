# On-Demand Download and Sync

## Overview

Pulp can sync content in a few modes: `immediate`, `on_demand`, and `streamed`. Each provides a
different behavior on how and when Pulp acquires content. These are set as the `policy` attribute
of the `Remote` performing the sync. Policy is an optional parameter and defaults to
`immediate`.

## Sync Modes

### immediate

When performing the sync, download all `Artifacts` now. Also download all metadata
now to create the content units in Pulp, associated with the
`repository version` created by the sync. `immediate` is the default, and
any plugin providing a sync is expected to implement the `immediate` mode.

### on_demand

When performing the sync, do not download any `Artifacts` now. Download all
metadata now to create the content units in Pulp, associated with the
`repository version` created by the sync. Clients requesting content
trigger the downloading of `Artifacts`, which are saved into Pulp to be served to
future clients.

This mode is ideal for saving disk space because Pulp never downloads and stores
`Artifacts` that clients don't need. Units created from this mode are
`on-demand content units<on-demand content>`.

### streamed

When performing the sync, do not download any `Artifacts` now. Download all
metadata now to create the content units in Pulp, associated with the
`repository version` created by the sync. Clients requesting content
trigger the downloading of `Artifacts`, which are *not* saved into Pulp. This
content will be re-downloaded with each client request.

This mode is ideal for content that you especially don't want Pulp to store over time. For
instance, syncing from a nightly repo would cause Pulp to store every nightly ever produced which
is likely not valuable. Units created from this mode are
`on-demand content units<on-demand content>`.

## Plugin support for on-demand/streamed

Unless a plugin has enabled either the 'on_demand' or 'streamed' values for the `policy` attribute
you will receive an error. Check that plugin's documentation also.

Example of the "Create Remote" endpoints for some plugins that supports these features:

* [pulp-rpm](https://pulpproject.org/pulp_rpm/restapi/#tag/Remotes:-Rpm/operation/remotes_rpm_rpm_create)
* [pulp-container](https://pulpproject.org/pulp_container/restapi/#tag/Remotes:-Container/operation/remotes_container_container_create)

!!! note
    Want to add on-demand support to your plugin? See the
    [On-Demand Support](site:pulpcore/docs/dev/learn/other/on-demand-support/)
    documentation for more details on how to add on-demand support to a plugin.


## On-Demand Content and Repository Versions

An `on-demand content unit` can be associated and unassociated from a `repository version` just like a normal unit. Note that the original `Remote` will be used to download content should a client request it, even as that content is
made available in multiple places.

!!! warning "Deleting a Remote"
    Learn about the dangers of [deleting a Remote](#remote-deletion-and-content-sharing) in the context of on-demand content.

## On-Demand and Streamed limitations

On-demand and streamed content can be useful, but they come with some problems.

### External dependency and error handling

There are two different types of errors that can occur with on-demand streaming:

1. **Pre-response**: Pulp can't find or connect to the server. A response is never started.
2. **Post-response**: Pulp can get data from the remote and start streaming the response, but the final digest is wrong.

(1) Pulp will try all the available remote sources for the requested content and will return a 404
if all of them fail with pre-response retriable errors.

(2) Pulp already sent the corrupted data to the client and can't recover from it, so it will close the connection to prevent the client from consolidating the file.
When this happens, the content-app will ignore that remote source for a [configurable cooldown interval],
which will enable future requests to select a different remote source.
If all remote sources are ignored due to prior failure, then a 404 will be returned for all requests of that content until the *cooldown interval* for one of those sources has expired.
Pulp doesn't permanently invalidate the remote because it can't know if the error is transient or not.

!!! info

    Case (2) is complex and can be confusing to the user.

    The core reason for this complexity lies in the very nature of on-demand serving, which imposes that Pulp must fetch and stream the content on request time, and has no way to know anything about the remote before that.
    This constrains the range of actions Pulp can do to satisfy the request properly.

    **If this behavior is prohibitive, consider using the immediate sync policy.**

Context: <https://github.com/pulp/pulpcore/issues/5012>.

### Remote deletion and content sharing

Deleting a `Remote` that was used in a sync with either the `on_demand` or `streamed`
options can break published data.

Specifically, clients who want to fetch content that a `Remote` was providing access to would begin to 404.
Recreating a `Remote` and re-triggering a sync will cause these broken units to recover again.

In the worst case, the Content is shared across multiple Repositories, and the Remote's removal
can invalidate all those repositories at once.

In either case, proceed with the deletion of a remote with great care.

Context: <https://github.com/pulp/pulpcore/issues/1975>.

### Implicit credential sharing within a domain

In the same domain, a request for on-demand content may use any available Remotes associated with that content,
regardless of which user created it.

An example:

* Given User A and User B both synced the same on-demand content from their separate remotes (there are two different sources for the same content).
* When User B requests the content
* Then the credentials used for the download could potentially be User A's.

If a user doesn't want their registered Remotes to be indirectly used by other users, they should use a separate domain.

Context: <https://github.com/pulp/pulpcore/issues/3212>.

[configurable cooldown interval]: site:pulpcore/docs/admin/reference/settings/#remote_content_fetch_failure_cooldown
