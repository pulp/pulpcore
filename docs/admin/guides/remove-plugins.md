# Remove Plugins

In case when one does not need a certain Pulp plugin anymore or there is a plugin which is no
longer supported and having it installed may prevent from upgrading to the latest releases for
pulpcore and other Pulp plugins.

Pulp provides an ability to remove its plugins. It might be needed for the following reasons:
: - a plugin is no longer needed

- a plugin is no longer supported (it can block further pulpcore upgrades if maintainers no
    longer update the plugin to be compatible with the latest pulpcore)

Plugins can be removed one at a time using the `pulpcore-manager` command `remove-plugin`. In this
example the File plugin is removed:

```
$ pulpcore-manager remove-plugin file
```

As a result, all the data related to the plugin will be removed from the Pulp database.
It is possible to install back the removed plugin if desired and if it's compatible with the
pulpcore version being used.

!!! note

    After `remove-plugin` command has succeeded, the plugin needs to be uninstalled manually.
    Steps to uninstall depend on how it was originally installed.
