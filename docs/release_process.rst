.. _pulpcore_release_process:

Pulpcore Release Process
========================

Here are the steps to take to release a Pulpcore version. New Y-releases of Pulpcore must take all of them.
**A new Z-release need only execute steps 2, 3, and 4.**

  * **"I am releasing a new Y-branch of Pulpcore (e.g., 3.23)"**:

    1. Via the Github Actions, trigger a `"Create new release branch" <https://github.com/pulp/pulpcore/actions/workflows/create-branch.yml>`_ job.

  * **"I am releasing a new Z-release of Pulpcore (e.g., 3.23.0, 3.22.12)"**:

    2. Via the Github Actions, trigger a `"Release pipeline" <https://github.com/pulp/pulpcore/actions/workflows/release.yml>`_ job by specifying the release branch (X.Y) and the tag (X.Y.Z) of the release.

    3. Once the release is available, make an announcement on Pulp discourse, in the "Announcements" category. See `example <https://discourse.pulpproject.org/t/pulpcore-3-21-0-is-now-available/626>`_.

    4. The CI automation will create PRs with the Changelog update and Versions bump that will need to be merged.

  * **"I have released a new Y-release of Pulpcore, followup actions"**:

    5. Arrange for a new oci-image for that release by following the `"oci-images Release Instructions" <https://github.com/pulp/pulp-oci-images/blob/latest/docs/developer-instructions.md>`_.

    6. Add the Y-release to ``ci_branches`` in `pulpcore's template.config.yml <https://github.com/pulp/pulpcore/blob/main/template_config.yml#L22>`_.

    7. Monitor `pulpcore pull-requests <https://github.com/pulp/pulpcore/pulls>`_ for creation of a PR such as `"Update supported versions" <https://github.com/pulp/pulp-ci/pull/826>`_. Such PRs are created by `this job <https://github.com/pulp/pulp-ci/actions/workflows/supported.yml>`_. The job may have been disabled if there hasn't been any release-activity in the repository for at least 60 days. You will need to re-enable it in this case.

Some possible failures of **Step 2**, above, include:

  * If release-tag is new but not based on current-dev, workflow will complain and fail

  * If release-tag is for an existing release (by accident) , the workflow won't fail until the docs-pub. Cleaning this up can be Exciting.