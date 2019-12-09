Glossary
========

.. glossary::

    :class:`~pulpcore.app.models.Artifact`
        A file. They usually belong to a :term:`content unit<content>` but may be used elsewhere
        (e.g. for PublishedArtifacts).

    :class:`~pulpcore.plugin.models.ContentGuard`
        A pluggable content protection mechanism that can be added to a :term:`Distribution`, and
        is used exclusively by the :term:`content app` to only hand out binary data to trusted
        clients. "Trusted users" are defined by the type of ContentGuard used.

    :class:`~pulpcore.app.models.Content`
    content unit
        Content are the smallest units of data that can be added and removed from
        :term:`repositories<repository>`. When singular, "content unit" should be used. Each
        content unit can have multiple :term:`artifacts<artifact>`. Each content unit has a
        :term:`type` (like .rpm or .deb) which that is defined by a :term:`plugin`.

    content app
        An `aiohttp.server <https://aiohttp.readthedocs.io/en/stable/web.html>`_ app provided by
        :term:`pulpcore` that serves :term:`content` through :term:`Distributions <distribution>`.

    :class:`~pulpcore.plugin.models.Distribution`
        User facing object that configures the :term:`content app` to serve either a
        :term:`Repository Version <RepositoryVersion>`, a :term:`Repository`, or a
        :term:`Publication<publication>`.

    Exporter
        Exporters can push a :term:`Repository Version <RepositoryVersion>`, a :term:`Repository`,
        or a :term:`Publication<publication>` content to a location outside of Pulp. Some example
        locations include a remote server or a file system location.

    on-demand content
        :term:`Content<content>` that was synchronized into Pulp but not yet saved to the
        filesystem. The Content's :term:`Artifacts<artifact>` are fetched at the time they are
        requested.  On-demand content is associated with a :term:`Remote` that knows how to download
        those :term:`Artifacts<artifact>`.

    plugin
        A `Django <https://docs.djangoproject.com>`_ app that exends :term:`pulpcore` to add more
        features to Pulp. Plugins are most commonly used to add support for one or more
        :term:`types<type>` of :term:`content`.

    :class:`~pulpcore.app.models.Publication`
        The metadata and :term:`artifacts<Artifact>` of the :term:`content units<content>` in a
        :term:`repository version<RepositoryVersion>`. Publications are served by the
        :term:`content app` when they are assigned to a :term:`distribution`.

    pulpcore
        A python package offering users a :doc:`rest_api` and plugin writers a
        :ref:`Plugin API`. It is :term:`plugin`-based and manages :term:`content`.

    PUP
        Stands for "Pulp Update Proposal", and are the documents that specify process changes for
        the Pulp project and community.

    :class:`~pulpcore.plugin.models.Remote`
        User facing settings that specify how Pulp should interact with an external :term:`content`
        source.

    :class:`~pulpcore.app.models.Repository`
        A versioned set of :term:`content units<content>`.

    :class:`~pulpcore.app.models.RepositoryVersion`
        An immutable snapshot of the set of :term:`content units<content>` that are in a
        :term:`repository`.

    sync
        A :term:`plugin` defined task that fetches :term:`content` from an external source using a
        :term:`remote`. The task adds and/or removes the :term:`content units<content>` to a
        :term:`repository`, creating a new :term:`repository version<RepositoryVersion>`.

    type
        Each :term:`content unit<content>` has a type (ex. rpm package or container tag) which is
        defined by a :term:`Plugin<plugin>`.
