.. _shared-attribute-management:

Managing Shared Attributes for Pulp Entities
--------------------------------------------

.. note::

    Pulp shared-attribute-management features are in tech-preview and may change in backwards incompatible
    ways in future releases.


Pulp provides the ability keep the attributes of entities "in sync" from a central manager.
For example, one may have many Remote objects that should all share the same concurrency,
socket-timeout, and rate-limit options. This feature lets you define those options in a
``SharedAttributeManager`` (SAM), add a list of entities that should have those attributes be
in sync, and arrange for all managed entities to be updated to the managed values.

A SAM consists of the following attributes:

    * ``name``, a unique identifier
    * ``managed_attributes``, a JSON structure defining the attributes being managed and the
      desired values
    * ``managed_sensitive_attributes``, a JSON structure defining any privacy/security sensitive attributes to
      be managed
    * ``managed_entities``, a list of pulp-HREFs of the entities whose attributes should be
      set to the values stored in ``managed_attributes`` and ``managed_sensitive_attributes``

.. note::

    For the remainder of this document, ``attributes`` will be used when "all attributes being managed, whether they
    are sensitive or not" is meant.

The ``managed_entities`` of a SAM can be a heterogeneous set of entities (e.g., several
different kinds of Detail Remotes), and its ``attributes`` can be an arbitrary set.
The SAM will only attempt to apply an attribute to a specific entity if that entity defines the attribute,
skipping any which do not apply.

If an attribute appears in both ``managed_attributes`` and ``managed_sensitive_attributes``, the value from
``managed_sensitive_attributes`` is preferred.

Because a user can put "anything" into ``managed_attributes`` and ``managed_sensitive_attributes``, both fields are
"encrypted at rest" in the database. Because ``managed_sensitive_attributes`` are assumed to be security-sensitive,
this field is ``write-only`` - it can be set, but is hidden from being read by the REST API.

The entities being managed are not tied to a managing SAM in any direct way; being added to
or removed from SAM-management does not impact the behavior of the specified entities.

Full documentation for the SAM REST API can be found at
`docs.pulpproject.org <https://docs.pulpproject.org/pulpcore/restapi.html/#tag/Shared-Attribute-Managers>`_. Examples
of the SAM workflow follow.

To create a SAM:

.. code-block::

    $ http POST :/pulp/api/v3/shared-attribute-managers/ name="MyManager"
    {
        "managed_attributes": null,
        "managed_entities": null,
        "name": "MyManager",
        "pulp_created": "2022-08-31T13:33:23.891003Z",
        "pulp_href": "/pulp/api/v3/shared-attribute-managers/ac6d3093-ac1e-4b3a-b30f-117e31abacad/"
    }

To show all existing SAMs:

.. code-block::

    $ http GET :/pulp/api/v3/shared-attribute-managers/
    {
        "count": 2,
        "next": null,
        "previous": null,
        "results": [
            {
                "managed_attributes": null,
                "managed_entities": null,
                "name": "SecondManager",
                "pulp_created": "2022-08-31T14:02:36.110474Z",
                "pulp_href": "/pulp/api/v3/shared-attribute-managers/1d84bb18-e3c6-4399-ba37-8d765fc9a8af/"
            },
            {
                "managed_attributes": null,
                "managed_entities": null,
                "name": "MyManager",
                "pulp_created": "2022-08-31T13:33:23.891003Z",
                "pulp_href": "/pulp/api/v3/shared-attribute-managers/ac6d3093-ac1e-4b3a-b30f-117e31abacad/"
            }
        ]
    }

To show a specific SAM:

.. code-block::

    $ http GET :/pulp/api/v3/shared-attribute-managers/ac6d3093-ac1e-4b3a-b30f-117e31abacad/
    {
        "managed_attributes": null,
        "managed_entities": null,
        "name": "MyManager",
        "pulp_created": "2022-08-31T13:33:23.891003Z",
        "pulp_href": "/pulp/api/v3/shared-attribute-managers/ac6d3093-ac1e-4b3a-b30f-117e31abacad/"
    }

To define the set of attributes to be shared, update a specific SAM with a JSON string defining
the attributes to be managed. This endpoint replaces the existing set of managed-attributes:

.. code-block::

    # SAM_HREF=/pulp/api/v3/shared-attribute-managers/949a0807-d79f-4821-b8de-8aadd32ac9ae/
    $ http --json PATCH :${SAM_HREF} \
        managed_attributes:='{"bar": "blech", "description": "This is a description", "retain_package_versions": 5, "sqlite_metadata": true, "url": "http://THIS-ONE-WORKS"}'
    {
        "managed_attributes": {
            "bar": "blech",
            "description": "This is a description",
            "retain_package_versions": 5,
            "sqlite_metadata": true,
            "url": "http://THIS-ONE-WORKS"
        },
        "managed_entities": null,
        "name": "foo",
        "pulp_created": "2022-08-29T20:35:06.090490Z",
        "pulp_href": "/pulp/api/v3/shared-attribute-managers/949a0807-d79f-4821-b8de-8aadd32ac9ae/"
    }

Similarly, to define a set of **sensitive** attributes to be shared, update a specific SAM with a JSON string defining
the attributes to be managed, and assign it to managed_sensitive_attributes. This endpoint replaces the existing set of
managed-sensitive-attributes. **Note** that the values are **not returned** from the REST call:

.. code-block::

    # SAM_HREF=/pulp/api/v3/shared-attribute-managers/949a0807-d79f-4821-b8de-8aadd32ac9ae/
    $ http --json PATCH :${SAM_HREF} managed_sensitive_attributes:='{"passsword": "DO NOT SHOW ME"}'
    {
        "managed_attributes": null,
        "managed_entities": null,
        "name": "foo",
        "pulp_created": "2022-08-29T20:35:06.090490Z",
        "pulp_href": "/pulp/api/v3/shared-attribute-managers/949a0807-d79f-4821-b8de-8aadd32ac9ae/"
    }


To add a set of entities to be managed, send an update to a specific SAM along with a list of the entity-hrefs. This
endpoint replaces the existing set of managed-entities:

.. code-block::

    $ http --json PATCH :/pulp/api/v3/shared-attribute-managers/949a0807-d79f-4821-b8de-8aadd32ac9ae/ \
      managed_entities:='["/pulp/api/v3/repositories/rpm/rpm/47a78cce-d947-45fe-a618-c139f288dd7f/", \
      "/pulp/api/v3/remotes/rpm/rpm/4507f854-e334-4f99-9c75-ee7621d64352/"]'
    {
        "managed_attributes": {
            "bar": "blech",
            "description": "This is a description",
            "retain_package_versions": 5,
            "sqlite_metadata": true,
            "url": "http://THIS-ONE-WORKS"
        },
        "managed_entities": [
            "/pulp/api/v3/repositories/rpm/rpm/47a78cce-d947-45fe-a618-c139f288dd7f/",
            "/pulp/api/v3/remotes/rpm/rpm/4507f854-e334-4f99-9c75-ee7621d64352/"
        ],
        "name": "foo",
        "pulp_created": "2022-08-29T20:35:06.090490Z",
        "pulp_href": "/pulp/api/v3/shared-attribute-managers/949a0807-d79f-4821-b8de-8aadd32ac9ae/"
    }

To add a new entity to be managed:

.. code-block::

    $ http -b POST :${SAM_HREF}add/ entity_href="/pulp/api/v3/repositories/file/file/daea11e9-b673-49f2-984a-b0de9278de01/"
    $ http -b :${SAM_HREF} | jq -r .managed_entities
    [
      "/pulp/api/v3/repositories/rpm/rpm/47a78cce-d947-45fe-a618-c139f288dd7f/",
      "/pulp/api/v3/remotes/rpm/rpm/4507f854-e334-4f99-9c75-ee7621d64352/"
      "/pulp/api/v3/repositories/file/file/daea11e9-b673-49f2-984a-b0de9278de01/"
    ]


To (re)apply all managed attributes to the current managed-entities list:

.. code-block::

    $ http -b POST :${SAM_HREF}apply/
    {
    "task": "/pulp/api/v3/tasks/7000fcae-99ae-4c76-bcdf-15ed7b277789/"
    }
    $ http :/pulp/api/v3/tasks/7000fcae-99ae-4c76-bcdf-15ed7b277789/
    {
        "child_tasks": [],
        "created_resources": [],
        "error": null,
        "finished_at": "2022-08-31T18:58:06.423795Z",
        "logging_cid": "b2a0f86bcafe4c92a321fa441ffc1baa",
        "name": "pulpcore.app.tasks.sam.update_managed_entities",
        "parent_task": null,
        "progress_reports": [
            {
                "code": "sam.apply",
                "done": 3,
                "message": "Updating Managed Entities",
                "state": "completed",
                "suffix": null,
                "total": 3
            },
            {
                "code": "sam.apply_success",
                "done": 3,
                "message": "Successful Updates",
                "state": "completed",
                "suffix": null,
                "total": 3
            },
            {
                "code": "sam.apply_failures",
                "done": 0,
                "message": "Failed Updates",
                "state": "completed",
                "suffix": null,
                "total": 3
            }
        ],
        "pulp_created": "2022-08-31T18:58:06.187955Z",
        "pulp_href": "/pulp/api/v3/tasks/7000fcae-99ae-4c76-bcdf-15ed7b277789/",
        "reserved_resources_record": [
            "/pulp/api/v3/repositories/rpm/rpm/47a78cce-d947-45fe-a618-c139f288dd7f/",
            "/pulp/api/v3/remotes/rpm/rpm/4507f854-e334-4f99-9c75-ee7621d64352/"
            "/pulp/api/v3/repositories/file/file/daea11e9-b673-49f2-984a-b0de9278de01/"
            "/pulp/api/v3/shared-attribute-managers/0754a264-06e4-4de9-a14f-b0a88e6a7ac1/"
        ],
        "started_at": "2022-09-01T18:58:06.227120Z",
        "state": "completed",
        "task_group": null,
        "worker": "/pulp/api/v3/workers/56cc8fa3-23f8-4b23-9c89-9d629471c217/"
    }

.. note::

    Any error while attempting to apply-changes will be recorded in the "sam.apply_failures" progress report. Specific
    failures, per entity, will be found in the ``task.error`` field.

    Example:

.. code-block::

    ...
    "error": {
        "/pulp/api/v3/shared-attribute-managers/405deeec-4846-4774-a897-049ebd1ff1a6/": "Validation errors: {'managed_attributes': [ErrorDetail(string='Expected a dictionary of items but got type \"str\".', code='not_a_dict')]}"
    },
    ...


To remove an entity from being managed:

.. code-block::

    $ http -b POST :${SAM_HREF}remove/ entity_href="/pulp/api/v3/repositories/rpm/rpm/47a78cce-d947-45fe-a618-c139f288dd7f/"
    "Removed /pulp/api/v3/repositories/rpm/rpm/47a78cce-d947-45fe-a618-c139f288dd7f/ from managed entities."

    $ http -b :${SAM_HREF} | jq -r .managed_entities
    [
      "/pulp/api/v3/remotes/rpm/rpm/4507f854-e334-4f99-9c75-ee7621d64352/"
      "/pulp/api/v3/repositories/file/file/daea11e9-b673-49f2-984a-b0de9278de01/"
    ]

Finally, to remove a SAM:

.. code-block::

    $ http DELETE :/pulp/api/v3/shared-attribute-managers/ac6d3093-ac1e-4b3a-b30f-117e31abacad/
    $

