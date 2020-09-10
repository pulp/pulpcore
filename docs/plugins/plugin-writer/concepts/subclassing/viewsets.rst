.. _subclassing-viewsets:

Viewsets
========

Each `Django Rest Framework Viewset <https://www.django-rest-framework.org/api-guide/viewsets/>`_
is a collection of views that provides ``create``, ``update``, ``retrieve``, ``list``, and
``delete``, which coresponds to http ``POST``, ``PATCH``, ``GET``, ``GET``, ``DELETE``,
respectively. Some base classes will not include all of the views if they are inappropriate. For
instance, the ``ContentViewset`` does not include ``update`` because Content Units are immutable in
Pulp 3 (to support Repository Versions).

Most Plugins will implement:
 * viewset(s) for plugin specific content type(s), should be subclassed from ``ContentViewSet``,
   ``ReadOnlyContentViewSet`` or ``SingleArtifactContentUploadViewSet``
 * viewset(s) for plugin specific remote(s), should be subclassed from ``RemoteViewSet``
 * viewset(s) for plugin specific publisher(s), should be subclassed from ``PublisherViewSet``


Endpoint Namespacing
--------------------

Automatically, each "Detail" class is namespaced by the ``app_label`` set in the
``PulpPluginAppConfig`` (this is set by the ``plugin_template``).

For example, a ContentViewSet for ``app_label`` "foobar" like this:

.. code-block:: python

    class PackageViewSet(ContentViewSet):
        endpoint_name = 'packages'

The above example will create set of CRUD endpoints for Packages at
``pulp/api/v3/content/foobar/packages/`` and
``pulp/api/v3/content/foobar/packages/<int>/``


Detail Routes (Extra Endpoints)
-------------------------------

In addition to the CRUD endpoints, a Viewset can also add a custom endpoint. For example:


.. code-block:: python

    class PackageViewSet(ContentViewSet):
        endpoint_name = 'packages'

        @decorators.detail_route(methods=('get',))
        def hello(self, request):
            return Response("Hey!")

The above example will create a simple nested endpoint at
``pulp/api/v3/content/foobar/packages/hello/``


.. _kick-off-tasks:

Kick off Tasks
^^^^^^^^^^^^^^

Some endpoints may need to deploy tasks to the tasking system. The following is an example of how
this is accomplished.

See :class:`~pulpcore.plugin.tasking.enqueue_with_reservation` for more details.

.. code-block:: python

        # We recommend using POST for any endpoints that kick off task.
        @detail_route(methods=('post',), serializer_class=RepositorySyncURLSerializer)
        # `pk` is a part of the URL
        def sync(self, request, pk):
            """
            Synchronizes a repository.
            The ``repository`` field has to be provided.
            """
            remote = self.get_object()
            serializer = RepositorySyncURLSerializer(data=request.data, context={'request': request})
            # This is how non-crud validation is accomplished
            serializer.is_valid(raise_exception=True)
            repository = serializer.validated_data.get('repository')
            mirror = serializer.validated_data.get('mirror', False)

            # This is how tasks are kicked off.
            result = enqueue_with_reservation(
                tasks.synchronize,
                [repository, remote],
                kwargs={
                    'remote_pk': remote.pk,
                    'repository_pk': repository.pk,
                    'mirror': mirror
                }
            )
            # Since tasks are asynchronous, we return a 202
            return OperationPostponedResponse(result, request)

If a "task_group" is provided as an optional keyword argument, then the deployed task will be
automatically added to the task group. Once done spawning new tasks for a given task group,
you should call ``.finish()`` on the task group object.

For more details about the reservation system and task groups, see :ref:`writing-tasks`. and
:class:`~pulpcore.plugin.models.TaskGroup`.


Content Upload ViewSet
^^^^^^^^^^^^^^^^^^^^^^

For single file content types, there is the special ``SingleArtifactContentUploadViewSet`` to
derive from, that allows file uploads in the create method, instead of referencing an existing
Artifact. Also it allows to specify a ``Repository``, to create a new ``RepositoryVersion``
containing the newly created content. Content creation is then offloaded into a task.
To use that ViewSet, the serializer for the content type should inherit from
``SingleArtifactContentUploadSerializer``. By overwriting the ``deferred_validate`` method
instead of ``validate``, this serializer can do detailed analysis of the given or uploaded Artifact
in order to fill database fields of the content type like "name", "version", etc. This part of
validation is only called in the task context.

If the uploaded content does not need to be stored, plugin writers may derive from the class
``NoArtifactContentUploadViewSet``. Again, the same analogy applies to this workflow. To use this
ViewSet, the associated serializer should also subclass ``NoArtifactContentUploadSerializer``. Note
that by using the aforesaid Serializer and ViewSet, Pulp still loads content of an uploaded file to
a temporary file. But the file is going to be removed by the end of a created task.

If any additional context needs to be passed from the ViewSet to the creation task, the
``get_deferred_context`` method of the ViewSet might be overwritten. It's return value will then be
available as ``self.context`` in the Serializer.

.. note::

   Context passed from the ViewSet to the Task must be easily serializable. i.e. one cannot
   return the request from ``get_deferred_context``.
