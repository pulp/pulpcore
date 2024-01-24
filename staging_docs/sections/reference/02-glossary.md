# Glossary

{class}`~pulpcore.app.models.Artifact`

: A file. They usually belong to a `content unit` but may be used
  elsewhere (e.g. for PublishedArtifacts).

{class}`~pulpcore.plugin.models.ContentGuard`

: A pluggable content protection mechanism that can be added to a `Distribution`, and
  is used exclusively by the `content app` to only hand out binary data to trusted
  clients. "Trusted users" are defined by the type of ContentGuard used.

{class}`~pulpcore.app.models.Content`
content unit

> Content are the smallest units of data that can be added and removed from
> `repositories`. When singular, "content unit" should be used. Each
> content unit can have multiple `artifacts`. Each content unit has a
> `type` (like .rpm or .deb) which that is defined by a `plugin`.

content app

: An [aiohttp.server](https://aiohttp.readthedocs.io/en/stable/web.html) app provided by
  `pulpcore` that serves `content ` through `Distributions
  <Distribution>`.

{class}`~pulpcore.plugin.models.Distribution`

: User facing object that configures the `content app` to serve either a
  `RepositoryVersion`, a `Repository`, or a `Publication`.

{class}`~pulpcore.plugin.models.Exporter`

: Exporters can push a `Repository Version `, a `Repository`,
  or a `Publication` content to a location outside of Pulp. Some example
  locations include a remote server or a file system location.

on-demand content

: `Content` that was synchronized into Pulp but not yet saved to the
  filesystem. The Content's `Artifacts` are fetched at the time they are
  requested.  On-demand content is associated with a `Remote` that knows how to download
  those `Artifacts`.

plugin

: A [Django](https://docs.djangoproject.com) app that exends `pulpcore` to add more
  features to Pulp. Plugins are most commonly used to add support for one or more
  `types` of `Content`.

{class}`~pulpcore.app.models.Publication`

: The metadata and `artifacts` of the `content units` in a
  `RepositoryVersion`. Publications are served by the `content app` when they are
  assigned to a `Distribution`.

pulpcore

: A python package offering users a {doc}`rest_api` and plugin writers a
  `plugin_api`. It is `plugin`-based and manages `Content`.

{class}`~pulpcore.plugin.models.Remote`

: User facing settings that specify how Pulp should interact with an external `Content`
  source.

{class}`~pulpcore.app.models.Repository`

: A versioned set of `content units`.

{class}`~pulpcore.app.models.RepositoryVersion`

: An immutable snapshot of the set of `content units` that are in a
  `Repository`.

sync

: A `plugin` defined task that fetches `Content` from an external source using a
  `Remote`. The task adds and/or removes the `content units` to a
  `Repository`, creating a new `RepositoryVersion`.

type

: Each `content unit` has a type (ex. rpm package or container tag) which is
  defined by a `Plugin`.

