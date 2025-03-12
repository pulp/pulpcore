# Introduction

Pulp uses [dynaconf](https://www.dynaconf.com/) for its settings which allows you
to configure Pulp settings using various ways:

- `Environment Variables <env-var-settings>` - Enabled by default.
- `Configuration File <config-file-settings>` - Disabled by default, but easy to enable.

!!! note "Available Settings"

    For a comprehensive list of core settings, refer to the
    [Settings Reference](site:pulpcore/docs/admin/reference/settings/).

    Plugin-specific settings are typically located in the corresponding Admin/Reference section

!!! note "Deployment-specific instructions"

    For specialized instruction on how to edit/set files and environment, check the guide appropriate to your deployment option:

    * [Container (single-process) quickstart](site:pulp-oci-images/docs/admin/tutorials/quickstart/#single-container)
    * [Container (multi-process) quickstart](site:pulp-oci-images/docs/admin/tutorials/quickstart/#podman-or-docker-compose)
    * [Pulp Operator quickstart](site:pulp-operator/docs/admin/tutorials/quickstart-kubernetes/)

## Configure

### Through Environment Variables

Configuration by specifying environment variables is enabled by default. Any
`Setting ` can be configured using Dynaconf by prepending `PULP_` to the setting
name. For example `SECRET_KEY <secret-key-setting>` can be specified as the `PULP_SECRET_KEY`
environment variable. For example, in a shell you can use `export` to set this:

```bash
export PULP_SECRET_KEY="This should be a 50 chars or longer unique secret!"
```

### Through Configuration File

By default, Pulp does not read settings from a configuration file. Enable this by specifying the
`PULP_SETTINGS` environment variable with the path to your configuration file. For example:

```bash
export PULP_SETTINGS=/etc/pulp/settings.py
```

Then you can specify settings with Python variable assignment in the `/etc/pulp/settings.py`. For
example, you can specify `SECRET_KEY <secret-key-setting>` with:

```bash
$ cat /etc/pulp/settings.py
SECRET_KEY="This should be a 50 chars or longer unique secret!"
```

In this example the settings file ends in ".py" so it needs to be valid Python, but it could use any
[dynaconf supported format](https://www.dynaconf.com/#supported-formats).

!!! note
    The configuration file and directories containing the configuration file must be readable by the
    user Pulp runs as. If using SELinux, assign the `system_u:object_r:pulpcore_etc_t:s0` label.


## View Settings

To view the effective settings on a Pulp installation you can use `dynaconf` commands.
Refer to the cli help for detailed usage instructions:

- `dynaconf list`: List all effective settings
- `dynaconf get -k <settings>`: Show value for a given key
- `dynaconf inspect -k <setting>`: Show debug info for a given key (e.g, load history)

For dynaconf to work, it'a required to set `DJANGO_SETTINGS_MODULE` to the django settings module location.
E.g, `export DJANGO_SETTINGS_MODULE=pulpcore.app.settings`.

The installations provided by Pulp will usually have that already set by default.

!!! note
    Settings can come from both settings file and environment variables. When running the
    `dynaconf list` command, be sure you have the same environment variables set as your Pulp
    installation.

