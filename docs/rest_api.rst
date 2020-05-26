REST API
========

.. note::

    The REST API documentation is `here <restapi.html>`_.

.. warning::
    Until Role-Based Access Control is added to Pulp, REST API is not safe for multi-user use.
    Sensitive credentials can be read by any user, e.g. ``Remote.password``, ``Remote.client_key``.

The documentation is auto generated based on the OpenAPI schema for the REST API. The hosted
documentation is broken up between ``pulpcore`` and each of the plugin's documentation sites.
Users can view the REST API documentation for their instance of Pulp by pointing their browser at
``http://<pulp-hostname>:24817/pulp/api/v3/docs/``.
