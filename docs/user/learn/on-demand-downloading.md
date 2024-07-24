# On-Demand Downloading

## Overview

Pulp can sync content in a few modes: 'immediate', 'on_demand', and 'streamed'. Each provides a
different behavior on how and when Pulp acquires content. These are set as the `policy` attribute
of the `Remote` performing the sync. Policy is an optional parameter and defaults to
`immediate`.

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

## Does Plugin X Support 'on_demand' or 'streamed'?

Unless a plugin has enabled either the 'on_demand' or 'streamed' values for the `policy` attribute
you will receive an error. Check that plugin's documentation also.

!!! note
    Want to add on-demand support to your plugin? See the
    [On-Demand Support](site:pulpcore/docs/dev/learn/other/on-demand-support/)
    documentation for more details on how to add on-demand support to a plugin.


## Associating On-Demand Content with Additional Repository Versions

An `on-demand content unit` can be associated and unassociated from a `repository version` just like a normal unit. Note that the original `Remote` will be used to download content should a client request it, even as that content is
made available in multiple places.

!!! warning
    Deleting a `Remote` that was used in a sync with either the `on_demand` or `streamed`
    options can break published data. Specifically, clients who want to fetch content that a
    `Remote` was providing access to would begin to 404. Recreating a `Remote` and
    re-triggering a sync will cause these broken units to recover again.

