# CLAUDE.md

The role of this file is to describe common mistakes and confusion points that agents might encounter as they work in this project.
If you ever encounter something in the project that surprises you, please alert the developer working with you and indicate that this is the case in the CLAUDE.md file to help prevent future agents from having the same issue.

## Interacting with the developer environment

Use the `pulp-cli` to interact with the Pulp API. Fallback on `httpie/curl` when the CLI doesn't support the endpoint/options needed.

```bash
pulp --help
pulp --refresh-api status
pulp file content list --limit 5
pulp file repository create --name foo
pulp -v file repository sync --name foo --remote foo
pulp task show --wait --href prn:core.task:019c8cae-cc5f-7148-a3de-456d0a9f39a1
pulp show --href /pulp/api/v3/tasks/019c8cae-cc5f-7148-a3de-456d0a9f39a1/
```

Use the `oci-env` cli to interact with the developer's Pulp instance. It has commands for managing state, running tests, and executing commands against a running Pulp.

```bash
oci-env --help
oci-env compose ps  # check status of the Pulp dev container
oci-env compose up/down/restart  # start/stop/restart the Pulp dev container
oci-env poll --attempts 10 --wait 10  # wait till Pulp container finishes booting up
oci-env pstart/pstop/prestart  # start/stop/restart the services inside the Pulp container
oci-env generate-client --help  # create the client bindings needed for the functional tests!
oci-env test --help # run the functional/unit tests
oci-env pulpcore-manager  # run any pulpcore or Django commands
```

## Running/Writing tests

Prefer writing functional tests for new changes/bugfixes and only fallback on unit tests when the change is not easily testable through the API.

pulpcore & pulp-file functional tests require both client bindings to be installed. The bindings must be regenerated for any changes to the API spec.

**Always** use the `oci-env` to run the functional and unit tests.

## Modifying template_config.yml

Use the `plugin-template` tool after any changes made to `template_config.yml`.

```bash
# typically located in the parent directory of pulpcore/plugin
../plugin_template/plugin-template --github
```

## Contributing

When preparing to commit and create a PR you **must** follow our [PR checklist](https://pulpproject.org/pulpcore/docs/dev/guides/pull-request-walkthrough/)
