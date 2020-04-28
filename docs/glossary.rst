Glossary
========

.. glossary::

    :class:`~pulpcore.app.models.Artifact`
        A file. They usually belong to a :term:`content unit<Content>` but may be used
        elsewhere (e.g. for PublishedArtifacts).

    :class:`~pulpcore.plugin.models.ContentGuard`
        A pluggable content protection mechanism that can be added to a :term:`Distribution`, and
        is used exclusively by the :term:`content app` to only hand out binary data to trusted
        clients. "Trusted users" are defined by the type of ContentGuard used.

    :class:`~pulpcore.app.models.Content`
    content unit
        Content are the smallest units of data that can be added and removed from
        :term:`repositories<Repository>`. When singular, "content unit" should be used. Each
        content unit can have multiple :term:`artifacts<Artifact>`. Each content unit has a
        :term:`type` (like .rpm or .deb) which that is defined by a :term:`plugin`.

    content app
        An `aiohttp.server <https://aiohttp.readthedocs.io/en/stable/web.html>`_ app provided by
        :term:`pulpcore` that serves :term:`content <Content>` through :term:`Distributions
        <Distribution>`.

    :class:`~pulpcore.plugin.models.Distribution`
        User facing object that configures the :term:`content app` to serve either a
        :term:`RepositoryVersion`, a :term:`Repository`, or a :term:`Publication`.

    :class:`~pulpcore.plugin.models.Exporter`
        Exporters can push a :term:`Repository Version <RepositoryVersion>`, a :term:`Repository`,
        or a :term:`Publication` content to a location outside of Pulp. Some example
        locations include a remote server or a file system location.

    on-demand content
        :term:`Content<Content>` that was synchronized into Pulp but not yet saved to the
        filesystem. The Content's :term:`Artifacts<Artifact>` are fetched at the time they are
        requested.  On-demand content is associated with a :term:`Remote` that knows how to download
        those :term:`Artifacts<Artifact>`.

    plugin
        A `Django <https://docs.djangoproject.com>`_ app that exends :term:`pulpcore` to add more
        features to Pulp. Plugins are most commonly used to add support for one or more
        :term:`types<type>` of :term:`Content`.

    :class:`~pulpcore.app.models.Publication`
        The metadata and :term:`artifacts<Artifact>` of the :term:`content units<Content>` in a
        :term:`RepositoryVersion`. Publications are served by the :term:`content app` when they are
        assigned to a :term:`Distribution`.

    pulpcore
        A python package offering users a :doc:`rest_api` and plugin writers a
        :ref:`Plugin API`. It is :term:`plugin`-based and manages :term:`Content`.

    PUP
        Stands for "Pulp Update Proposal", and are the documents that specify process changes for
        the Pulp project and community.

    :class:`~pulpcore.plugin.models.Remote`
        User facing settings that specify how Pulp should interact with an external :term:`Content`
        source.

    :class:`~pulpcore.app.models.Repository`
        A versioned set of :term:`content units<Content>`.

    :class:`~pulpcore.app.models.RepositoryVersion`
        An immutable snapshot of the set of :term:`content units<Content>` that are in a
        :term:`Repository`.

    sync
        A :term:`plugin` defined task that fetches :term:`Content` from an external source using a
        :term:`Remote`. The task adds and/or removes the :term:`content units<Content>` to a
        :term:`Repository`, creating a new :term:`RepositoryVersion`.

    type
        Each :term:`content unit<Content>` has a type (ex. rpm package or container tag) which is
        defined by a :term:`Plugin<plugin>`.
