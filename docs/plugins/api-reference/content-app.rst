.. _content-app-docs:

pulpcore.plugin.content
=======================

The Content app provides built-in functionality to handle user requests for content, but in some
cases the default behavior may not work for some content types. For example, Container content requires
specific response headers to be present. In these cases the plugin write should provide a custom
Handler to the Content App by subclassing `pulpcore.plugin.content.Handler`.

Making a custom Handler is a two-step process:

1. subclass `pulpcore.plugin.content.Handler` to define your Handler's behavior
2. Add the Handler to a route using aiohttp.server's `add_route() <https://aiohttp.readthedocs.io/en
   /stable/web_reference.html#aiohttp.web.UrlDispatcher.add_route>`_ interface.

If content needs to be served from within the :term:`Distribution`'s base_path,
overriding the :meth:`~pulpcore.plugin.models.BaseDistribution.content_handler` and
:meth:`~pulpcore.plugin.models.BaseDistribution.content_handler_directory_listing`
methods in your Distribution is an easier way to serve this content.

Creating your Handler
---------------------

Import the Handler object through the plugin API and then subclass it. Custom functionality can be
provided by overriding the various methods of `Handler`, but here is the simplest version:

.. code-block:: python

    from pulpcore.plugin.content import Handler

    class MyHandler(Handler):

        pass

Here is an example of the `Container custom Handler <https://github.com/pulp/pulp_container/blob/master/
pulp_container/app/registry.py>`_.


Registering your Handler
------------------------

We register the Handler with Pulp's Content App by importing the aiohttp.server 'app' and then
adding a custom route to it. Here's an example:

.. code-block:: python

    from pulpcore.content import app

    app.add_routes([web.get(r'/my/custom/{somevar:.+}', MyHandler().stream_content)])


Here is an example of `Container registering some custom routes <https://github.com/pulp/pulp_container/
blob/master/pulp_container/app/content.py>`_.


Restricting which detail Distributions Match
--------------------------------------------

To restrict which Distribution model types your Handler will serve, set the `distribution_model`
field to your Model type. This causes the Handler to only search/serve your Distribution types.

.. code-block:: python

    from pulpcore.plugin.content import Handler

    from models import MyDistribution


    class MyHandler(Handler):

        distribution_model = MyDistribution


pulpcore.plugin.content.Handler
-------------------------------

.. autoclass:: pulpcore.plugin.content.Handler
