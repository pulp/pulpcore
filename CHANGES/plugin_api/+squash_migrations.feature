Pulpcore migrations have been squashed.
In order to allow removing the old ones, plugins should rebase their migrations on at least the 0091 migration of core.
The `pulpcore-manager rebasemigrations` command will hep with that.
