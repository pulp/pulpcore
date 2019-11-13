Added `Repository.finalize_new_version(new_version)` which is called by `RepositoryVersion.__exit__`
to allow plugin-code to validate or modify the `RepositoryVersion` before pulpcore marks it as
complete and saves it.

Added `pulpcore.plugin.repo_version_utils.remove_duplicates(new_version)` for plugin writers to use.
It relies on the definition of repository uniqueness from the `repo_key_fields` tuple plugins can
define on their `Content` subclasses.
