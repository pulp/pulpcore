# Alternate Content Sources

!!! warning
    This feature requires plugin support to work correctly.


## Overview

Pulp supports the concept of Alternate Content Sources (ACS) which sync content using a remote.
Each content source is a potential alternate provider of files that are associated with content
units in Pulp.

The ACS are useful when dealing with an unreliable or slow internet connection to remote
repositories. Also, when some parts of the repositories are already present on the local
filesystem, configuring a remote pointing to, e.g., `file://path/to/the/repo` enables the
related ACS to fetch the content faster. Similarly, if there exists a mirror of a CDN that is known
to be geographically closer to clients, the ACS may come to the place as well.

Setting the ACS tells Pulp to first check for alternative sources of content in an attempt to pull
the remote content. The ACS have a global scope. Thus, alternative sources will be used in all
future synchronization tasks regardless of the remote specified during the sync time as long as the
checksums of remote artifacts match.

## Creating ACS

To create ACS, you'll need a Remote with the "on_demand" policy. You can have ACS point to
multiple Repositories by specifying the `paths` parameter. Each path will be appended to the
Remote's url.

```
pulp <plugin_name> acs create --name <acs_name> --remote <remote> --path <path> --path <path>
```

!!! note
    The `path` option is optional and can be specified multiple times. If a path is not provided,
    the url of your remote is used to search for content.


## Updating ACS

To update ACS, use a similar call to your ACS but with `update` command:

```
pulp <plugin_name> acs update --name <acs_name> --remote <remote>
```

To add or remove paths, use the `path` subcommand:

```
pulp <plugin_name> acs path add --name <acs_name> --path <path>
pulp <plugin_name> acs path remove --name <acs_name> --path <path>
```

## Refreshing ACS

To make ACS available the next time you sync, you will need to call the `refresh` command.  It
will go through your paths and catalog content from your content source.

```
pulp <plugin_name> acs refresh --name <acs_name>
```
