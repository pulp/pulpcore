# Update Repository Version Retention

Repositories in Pulp 3 are versioned and anytime a change is made to the content of Repository, a
new version is created. These RepositoryVersions are immutable: they can only be created and
deleted, not updated or changed.

## Version Retention

By default,`retain_repo_versions` is null which means that Pulp will store all versions of a
Repository. This behavior can be changed by setting the retain_repo_versions field on the
Repository. A Repository must have at least one RepositoryVersion so `retain_repo_versions` must be
greater than or equal to 1.

Setting retain_repo_versions to 1 effectively disables repository versioning since Pulp will only
store the latest version.

Cleanup will ignore any repo versions that are being served directly via a distribution or via a
publication.

To update this field for a file Repository called myrepo, simply call:

```
pulp file repository update --name myrepo --retained-versions 1
```

Note that updating this field will automatically update the versions for the Repository so setting
the number to a smaller value will cause Pulp to delete any versions that exceed the number of
retained versions.
