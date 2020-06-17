.. _content-protection:

Content Protection
------------------

By default, the Content app will serve all content, but some deployments want to only serve content
to some users and not others. For example pulp_rpm only wants to give rpms to users who have valid
certificates declaring their paid access to content. To allow total customization of how content is
protected, A plugin writer can define a ``ContentGuard``.


Defining a ContentGuard
^^^^^^^^^^^^^^^^^^^^^^^

The ``ContentGuard`` is a Master/Detail object provided at
``from pulpcore.plugin.models import ContentGuard``, which provides `these base fields <https://
github.com/pulp/pulpcore/blob/master/pulpcore/app/models/publication.py#L192-L202>`_.

In your plugin code, subclass ``ContentGuard`` and optionally add additional fields as necessary to
perform the authentication and authorization. Then overwrite the ``permit`` method so that it
returns ``None`` if access is granted and throws a ``PermissionError`` on denial. As with all
Master/Detail objects a ``TYPE`` class attribute is needed which is then used in the URL. For
``ContentGuard`` detail objects the URL structure is::

    ``/pulp/api/v3/contentguards/<plugin_name>/<TYPE>/``


.. note::

   The `pulp-certguard <https://pulp-certguard.readthedocs.io/en/latest/>`_ plugin ships various
   ``ContentGuard`` types for users and plugin writers to use together. Plugins can ship their own
   content guards too, but look at the existing ones first.


Simple Example
^^^^^^^^^^^^^^

Here's a trivial example where the client needs to send a header named SECRET_STRING and if its
value matches a recorded value for that ContentGuard instance, give the content to the user. The
secret both authenticates the user and authorizes them for this Content.

.. code-block:: python

   from django.db import models
   from pulpcore.plugin.models import ContentGuard

   class SecretStringContentGuard(ContentGuard):

       TYPE = 'secret_string'

       secret_string = models.FileField(max_length=255)

       def permit(self, request):
           """

           Authorize the specified web request.

           Args:
               request (aiohttp.web.Request): A request for a published file.

           Raises:
               PermissionError: When the request cannot be authorized.
           """
           ca = self.ca_certificate.read()
           validator = Validator(ca.decode('utf8'))
           validator(request)

       class Meta:
           default_related_name = "%(app_label)s_%(model_name)s"


End-User use of ContentGuard
############################

Users create an instance of a ``SecretStringContentGuard`` and give it a secret string with
``httpie``::

   http POST http://localhost:24817/pulp/api/v3/contentguards/<plugin_name>/secret_string/ \
                 secret_string='2xlSFgJwOhbLrtIlmYszqHQy7ivzdQo9'


Then the user can protect one or more Distributions by specifying ``content_guard``. See the
`ContentGuard creation API <https://docs.pulpproject.org/restapi.html#operation/
distributions_file_file_create>`_ for more information.


.. _plugin-writers-use-content-protection:

Plugin Writer use of ContentGuard
#################################

Plugin writers can also programatically create detail ``ContentGuard`` instances and have the
plugin's detail Distribution they define force its use. This allows plugin writers to offer
content protection features to users with fewer user required steps.
