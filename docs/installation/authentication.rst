.. _authentication:

API Authentication
==================

By default, Pulp supports Basic and Session authentication. The Basic Authentication checks the
username and password against the internal users database.

.. note::
    This authentication is only for the REST API. Client's fetching binary data have their identity
    verified and authorization checked using a :term:`ContentGuard`.

.. warning::
    Until Role-Based Access Control is added to Pulp, REST API is not safe for multi-user use.
    Sensitive credentials can be read by any user, e.g. ``Remote.password``, ``Remote.client_key``.

Which URLs Require Authentication?
----------------------------------

All URLs in the REST API require authentication except the Status API, ``/pulp/api/v3/status/``,
which is served to unauthenticated users too. This is true regardless of the type of authentication
you configure.


Concepts
--------

Authentication in Pulp is provided by Django Rest Framework and Django together.

Django provides the
`AUTHENTICATION_BACKENDS <https://docs.djangoproject.com/en/2.2/ref/settings/#std:setting-AUTHENTICATION_BACKENDS>`_
which defines a set of behaviors to check usernames and passwords against.

Django Rest Framework defines the source usernames and passwords come from with the
`DEFAULT_AUTHENTICATION_CLASSES <https://www.django-rest-framework.org/api-guide/authentication/#setting-the-authentication-scheme>`_
setting.


Basic Authentication
--------------------

Pulp by default uses `Basic Authentication <https://tools.ietf.org/html/rfc7617>`_ which checks the
user submitted header against an internal database of users. If the username and password match, the
request is considered authenticated as that username.

Below is an example of a Basic Authentication header::

    Authorization: Basic YWRtaW46cGFzc3dvcmQ=

You can set this header on an `httpie <https://httpie.org/>`_ command as follows::

    http :80/pulp/api/v3/tasks/ Authorization:"Basic YWRtaW46cGFzc3dvcmQ="

.. warning::

    For the 3.0 release, Pulp expects the user table to have exactly 1 user in it named 'admin',
    which is created automatically when the initial migration is applied. The password for this user
    can be set with the ``pulpcore-manager reset-admin-password`` command.
    To articulate what you'd like to see future versions of Pulp file a feature request
    `here <https://pulp.plan.io/projects/pulp/issues/new>`_ or reach out via
    `pulp-list@redhat.com <https://www.redhat.com/mailman/listinfo/pulp-list>`_.


Disabling Basic Authentication
******************************

Basic Authentication is defined by receiving the username and password encoded in the
``Authorization`` header. To disable receiving the username and password using Basic Authentication,
remove the ``rest_framework.authentication.BasicAuthentication`` from the
``REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']`` list.


Disabling Checks against Internal User DB
-----------------------------------------

The internal users database is checked using the ``django.contrib.auth.backends.ModelBackend`` from
Django. To disable checking a username and password against the internal users database, remote the
``django.contrib.auth.backends.ModelBackend`` from the ``AUTHENTICATION_BACKENDS`` setting in Pulp.

You can do this effectively, for example using a Python settings file::

    AUTHENTICATION_BACKENDS = []


Or as an by defining an environment variable for Dynaconf to use::

    export PULP_AUTHENTICATION_BACKEND="[]"


.. _webserver-auth:

Webserver Authentication
------------------------

Pulp can be configured to use authentication provided in the webserver outside of Pulp. This allows
for integration with ldap for examples, through
`mod_ldap <https://httpd.apache.org/docs/2.4/mod/mod_ldap.html>`_, or certificate based API access,
etc.

Enable external authentication in two steps:

1. Accept external auth instead of checking the internal users database by enabling::

    ``AUTHENTICATION_BACKENDS = ['pulpcore.app.authentication.PulpNoCreateRemoteUserBackend']``.

This will cause Pulp to accept any username for each request and not create a user in the database
backend for them. To have any name accepted but create the username in the database backend, use the
``django.contrib.auth.backends.RemoteUserBackend`` instead, which creates users by default.


2. Specify how to receive the username from the webserver. Do this by specifying to DRF an
   AUTHENTICATION_CLASS. For example, use the ``PulpRemoteUserAuthentication`` as follows::

    REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = (
        'rest_framework.authentication.SessionAuthentication',
        'pulpcore.app.authentication.PulpRemoteUserAuthentication'
    )

This removes ``rest_framework.authentication.BasicAuthentication``, and adds
``PulpRemoteUserAuthentication`` which accepts the username as WSGI environment variable
``REMOTE_USER`` by default, but can be configured via the
`REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>`_ Pulp setting.


.. _webserver-auth-same-webserver:

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

See the `REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>`_ for configuring the WSGI provided
name, but if you are using the ``REMOTE_USER`` WSGI environment name with "same webserver"
authentication, you likely want to leave `REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>`_
unset and configure the webserver to set the ``REMOTE_USER`` WSGI environment variable.


.. _webserver-auth-with-reverse-proxy:

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

Pulp provides a setting named `REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>`_ which allows
you to specify another WSGI environment variable to read the authenticated username from.

.. warning::

    Configuring this has serious security implications. See the `Django warning at the end of this
    section in their docs <https://docs.djangoproject.com/en/2.2/howto/auth-remote-user/
    #configuration>`_ for more details.


Custom Authentication
---------------------

Pulp is a Django app and Django Rest Framework (DRF) application, so additional authentication can
be added as long as it's correctly configured for both Django and Django Rest Frameowork.

See the `Django docs on configuring custom authentication <https://docs.djangoproject.com/en/2.2/
topics/auth/customizing/#customizing-authentication-in-django>`_ and the `Django Rest Framework docs
on configuring custom authentication <https://www.django-rest-framework.org/api-guide/authentication
/#custom-authentication>`_.
