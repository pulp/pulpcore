.. _pulpcore_release_process:

Pulpcore Release Process
========================

Here are the steps to take to release a minor Pulpcore version, e.g. 3.21.0:

1. Via the Github Actions, trigger a `"Create new release branch" <https://github.com/pulp/pulpcore/actions/workflows/create-branch.yml>`_ job.
2. Via the Github Actions, trigger a `"Release pipeline" <https://github.com/pulp/pulpcore/actions/workflows/release.yml>`_ job
   by specifying the release branch and the tag of the release.
3. Once the release is available, make an anouncement on the discourse. See `example <https://discourse.pulpproject.org/t/pulpcore-3-21-0-is-now-available/626>`_.
4. The CI automation will create PRs with the Changelog update and Versions bump that will need to
   be merged.

To release a patch Pulpcore version, e.g. 3.21.1, follow same steps except for the first one.
