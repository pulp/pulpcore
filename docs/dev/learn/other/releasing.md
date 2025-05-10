# Releasing Your Plugin

## Depending on pulpcore

The Plugin API is not yet stable, but starting with pulpcore 3.7.0, a
`deprecation process ` is in place which makes it safe for a plugin
to declare compatability with the next, unreleased pulpcore version also. For example, a plugin
compatible with pulpcore 3.7 would declare compatibility up to pulpcore 3.8. In this example, use
the following requirements string:

```
pulpcore>=3.7,<3.9
```

This ensures that when pulpcore 3.8 is released, users can receive it immediately and use it without
any issue. However when 3.9 comes out, any deprecations introduced in the `pulpcore.plugin` API in
3.8 will be removed, so preventing your plugin from working with pulpcore 3.9 maintains
compatibility.

Sometimes plugins can be compatible with older version of pulpcore, and in those cases the oldest
version should be allowed. For example if your plugin is compatible with pulpcore 3.5, and you just
tested it against 3.7 and it's still compatible, use this requirements string:

```
pulpcore>=3.5,<3.9
```

## Release process

Here are the steps to take to release a minor Plugin version, e.g. pulp_file 1.11.0:

1. Via the Github Actions, trigger a ["Create new release branch"](https://github.com/pulp/pulpcore/actions/workflows/create-branch.yml) job.

1. Checkout locally the target plugin release branch and set accordingly `pulpcore_branch` and
    `pulpcore_pip_version_specifier` in the template_config file.

1. Pull in latest CI changes from the plugin_template. Ensure you have the latest copy of upstream
    remote.

    ```
    [user@localhost plugin_template]$ git remote -v
    origin      git@github.com:user/plugin_template.git (fetch)
    origin      git@github.com:user/plugin_template.git (push)
    upstream    git@github.com:pulp/plugin_template.git (fetch)
    upstream    git@github.com:pulp/plugin_template.git (push)
    [user@localhost plugin_template]$ git branch
    * main
    [user@localhost plugin_template]$ git pull upstream main
    [user@localhost plugin_template]$ ./plugin-template --github <plugin_name>
    ```

    Make the PR against target plugin release branch and merge it.

1. Via the Github Actions, trigger a ["Release pipeline"](https://github.com/pulp/pulpcore/actions/workflows/release.yml) job
    by specifying the release branch and the tag of the release.

1. Once the release is available, make an anouncement on the discourse. See [example](https://discourse.pulpproject.org/t/pulp-file-1-11-0-has-been-released/551/2) .

1. The CI automation will create PRs with the Changelog update and Versions bump that will need to
    be merged.

To release a patch Plugin version, e.g. pulp_file 1.11.1, start with the step number 4.
