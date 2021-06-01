.. _webserver-authentication:

Webserver
---------

Pulp can be configured to use authentication provided in the webserver outside of Pulp. This allows
for integration with ldap for example, through `mod_ldap <https://httpd.apache.org/docs/2.4/mod/
mod_ldap.html>`_, or certificate based API access, etc.

Enable external authentication in two steps:

1. Accept external auth instead of checking the internal users database by enabling::

    ``AUTHENTICATION_BACKENDS = ['pulpcore.app.authentication.PulpNoCreateRemoteUserBackend']``.

This will cause Pulp to accept any username for each request and not create a user in the database
backend for them. To have any name accepted but create the username in the database backend, use the
``django.contrib.auth.backends.RemoteUserBackend`` instead, which creates users by default.


2. Specify how to receive the username from the webserver. Do this by specifying to DRF an
   ``AUTHENTICATION_CLASS``. For example, use the ``PulpRemoteUserAuthentication`` as follows::

    REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = (
        'rest_framework.authentication.SessionAuthentication',
        'pulpcore.app.authentication.PulpRemoteUserAuthentication'
    )

   Or, as a dynaconf environment variable (pay special attention to the *double* underscore
   separating the paramater name from the key)::

    PULP_REST_FRAMEWORK__DEFAULT_AUTHENTICATION_CLASSES="[
      'rest_framework.authentication.SessionAuthentication',
      'pulpcore.app.authentication.PulpRemoteUserAuthentication'
    ]"

This removes ``rest_framework.authentication.BasicAuthentication``, but retains
``rest_framework.authentication.SessionAuthentication`` and adds
``PulpRemoteUserAuthentication``. This accepts the username as WSGI environment variable
``REMOTE_USER`` by default, but can be configured via the
:ref:`REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>` Pulp setting.


.. _webserver-authentication-same-webserver:

Webserver Auth in Same Webserver
********************************

If your webserver authentication is occurring in the same webserver that is serving the
``pulpcore.app.wsgi`` application, you can pass the authenticated username to Pulp via the WSGI
environment variable ``REMOTE_USER``.

Reading the ``REMOTE_USER`` WSGI environment is the default behavior of the
``pulpcore.app.authentication.PulpRemoteUserAuthentication`` and the Django Rest Framework provided
``rest_framework.authentication.RemoteUserAuthentication``. The only difference in the Pulp provided
one is that the WSGI environment variable name can be configured from a Pulp provided WSGI
environment variable name.

See the :ref:`REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>` for configuring the WSGI provided
name, but if you are using the ``REMOTE_USER`` WSGI environment name with "same webserver"
authentication, you likely want to leave :ref:`REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>`
unset and configure the webserver to set the ``REMOTE_USER`` WSGI environment variable.


.. _webserver-authentication-with-reverse-proxy:

Webserver Auth with Reverse Proxy
*********************************

For example purposes, assume you're using Nginx with LDAP authentication required and after
authenticating it reverse proxies your request to the gunicorn process running the pulpcore.app.wsgi
application. That would look like this::

    nginx <---http---> gunicorn <----WSGI----> pulpcore.app.wsgi application


With nginx providing authentication, all it can do is pass ``REMOTE_USER`` (or similar name) to the
application webserver, i.e. gunicorn. You can pass the header as part of the proxy request in nginx
with a config line like::

    proxy_set_header REMOTE_USER $remote_user;

Per the `WSGI standard <https://www.python.org/dev/peps/pep-0333/#environ-variables>`_, any incoming
headers will be prepended with a ``HTTP_``. The above line would send the header named
``REMOTE_USER`` to gunicorn, and the WSGI application would receive it as ``HTTP_REMOTE_USER``. The
default configuration of Pulp is expecting ``REMOTE_USER`` in the WSGI environment not
``HTTP_REMOTE_USER``, so this won't work with
``pulpcore.app.authentication.PulpRemoteUserAuthentication`` or the Django Rest Framework provided
``rest_framework.authentication.RemoteUserAuthentication`` as is.

Pulp provides a setting named :ref:`REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>` which allows
you to specify another WSGI environment variable to read the authenticated username from.

.. warning::

    Configuring this has serious security implications. See the `Django warning at the end of this
    section in their docs <https://docs.djangoproject.com/en/2.2/howto/auth-remote-user/
    #configuration>`_ for more details.
