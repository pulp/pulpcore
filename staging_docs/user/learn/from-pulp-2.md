# Changes From Pulp 2

## Renamed Concepts

### Importers -> Remotes

CLI users may not have been aware of Importer objects because they were embedded into CLI commands
with repositories. In Pulp 3, this object is now called a `Remote`. The scope of this object
has been reduced to interactions with a single external source. They are no longer associated with a
repository.

### Distributors -> Publication/Exporters

CLI users may not have been aware of Distributor objects because they were also embedded into CLI
commands with repositories. In some cases these distributors created metadata along with the
published content, e.g. `YumDistributor`. In other cases, Distributor objects pushed content to
remote services, such as the `RsyncDistributor`.

For Pulp 2 Distributors that produce metadata, e.g. `YumDistributor`, Pulp 3 introduces a
`Publication` that stores content and metadata created describing that content. The
responsibilities of serving a `Publication` are moved to a new object, the
`Distribution`. Only plugins that need metadata produced at publish time will have use
`Publications`.

For Pulp 2 Distributors that push content to remote systems, e.g. `RsyncDistributor`, Pulp 3
introduces an `Exporter` that is used to push an existing `Publication` to a remote
location. For content types that don't use `Publications`, exporters can export
`RepositoryVersion` content directly.

## New Concepts

### Repository Version

A new feature of Pulp 3 is that the content set of a repository is versioned. Each time the content
set of a repository is changed, a new immutable `RepositoryVersion` is created. An empty
`RepositoryVersion` is created upon creation of a repository.

### Rollback

The combination of publications and distributions allows users to promote and rollback instantly.
With one call, the user can update a distribution (eg. "Production") to host any pre-created
publication.

### Going Live is Atomic

Content is served by a `Distribution` and goes live from Pulp's `content app` as soon as
the database is configured to serve it. This guarantees a users view of a repository is consistent
and as the entire repository is made available atomically.

## Obsolete Concepts

### Consumers

In Pulp 2, there are consumers, aka managed hosts. It is information about existing installation
and subscription profiles for hosts which receive updates based on Pulp repositories. This is
not supported in Pulp 3. The functionality is available as part of [the Katello project](https://theforeman.org/plugins/katello/).

### Applicability

Applicability is a feature that provides a list of updates, content which needs to be installed
on a specific host to bring it up to date. In Pulp 2, it is possible to calculate applicability
based on the installation and subscription profile of a host managed by Pulp. This is
not supported in Pulp 3. The functionality is available as part of [the Katello project](https://theforeman.org/plugins/katello/).

## Scheduling Tasks

While Pulp 2 supported scheduling tasks natively, this is no longer a core feature in Pulp 3. Scheduling Pulp tasks
in Pulp 3 can be accomplished using any of the following external tools (and possibly others not on this list).

- [cron](http://pubs.opengroup.org/onlinepubs/9699919799/utilities/crontab.html)
- [rundeck](http://rundeck.org/)
- [distributed cron](https://github.com/ivanmp91/distributed-cron)
