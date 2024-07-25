# About File Repositories

This is the `pulp_file` Plugin for [Pulp Project
3.0+](https://pypi.org/project/pulpcore/). This plugin replaces the ISO support in the
`pulp_rpm` plugin for Pulp 2.

## Overview

A `pulp_file` repository consists of a list of arbitrary files, along with a `PULP_MANIFEST` file.
The `PULP_MANIFEST` consists of one line per file, each line with the format
`filename,sha256-checksum,size-in-bytes` . Pulp creates a PULP_MANIFEST when you [publish](site:/pulp_file/docs/user/guides/02-publish-host/)
a repository.

If you are setting up a directory that you wish to make available to Pulp to synchronize, it will need
to have its own `PULP_MANIFEST`. You can take advantage of the
[pulp-manifest tool](https://github.com/pulp/pulp-manifest/) to create one for you from an existing directory
of files to be served.
