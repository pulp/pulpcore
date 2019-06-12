.. _authentication:

API Authentication
==================

By default, Pulp has two types of authentication enabled, and both are tried before rejecting a
request as unauthenticated.

   1. Basic Authentication, which is checked against an internal users database
   2. Webserver authentication that relies on the webserver to perform the authentication.

.. note::
    This authentication is only for the REST API. Client's fetching binary data have their identity
    verified and authorization checked using a :term:`ContentGuard`.


Which URLs Require Authentication?
----------------------------------

All URLs in the REST API require authentication except the Status API, ``/pulp/api/v3/status/``,
which is served to unauthenticated users too. This is true regardless of the type of authentication
you configure.


Basic Auth
----------

Pulp by default uses `Basic Auth <https://tools.ietf.org/html/rfc7617>`_ authentication which checks
the user submitted header against an internal database of users. If the username and password match,
the request is considered authenticated as that username.

.. warning::

    For the 3.0 release, Pulp expects the user table to have exactly 1 user in it named 'admin',
    which is created automatically when the initial migration is applied. The password for this user
    can be set with the ``django-admin reset-admin-password`` command, but defaults to 'password'.
    To articulate what you'd like to see future versions of Pulp file a feature request
    `here <https://pulp.plan.io/projects/pulp/issues/new>`_ or reach out via
    `pulp-list@redhat.com <https://www.redhat.com/mailman/listinfo/pulp-list>`_.


Disabling Basic Auth
********************

To disable Basic Auth, remove the ``'django.contrib.auth.backends.ModelBackend'`` from the
``AUTHENTICATION_BACKENDS`` setting in Pulp.

You can configure Django Rest Framework to not trust users authenticated with Basic Auth by removing
``'rest_framework.authentication.BasicAuthentication'`` from the
``REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']`` .


.. _webserver-auth:

Webserver Auth
--------------

Pulp by default can use authentication configured in the webserver, e.g. Apache 2.4 configured with
`mod_ldap <https://httpd.apache.org/docs/2.4/mod/mod_ldap.html>`_. By default Pulp trusts a WSGI
environment variable named ``REMOTE_USER``, and will create a Django user in the user list to
represent that user. These are the typical behaviors provided by Django's `REMOTE_USER middleware
<https://docs.djangoproject.com/en/2.2/howto/auth-remote-user/>`_ which is enabled by default with
Pulp.


.. _webserver-auth-with-reverse-proxy:

Webserver Auth with Reverse Proxy
*********************************

For example purposes, assume you're using Nginx with LDAP authentication required and after
authenticating it reverse proxies your request to the gunicorn process running the pulpcore.app.wsgi
application. That would look like this::

    nginx <----> gunicorn <----> pulpcore.app.wsgi application


With nginx knowing ``REMOTE_USER`` and acting as a proxy it can't set the environment variable
for the wsgi request because that happens in gunicorn. To give the REMOTE_USER information to Pulp
a header should be used, and the nginx config should include a line like::

    proxy_set_header REMOTE_USER $remote_user;

Per the `WSGI standard <https://www.python.org/dev/peps/pep-0333/#environ-variables>`_, any incoming
headers will be prepended with a ``HTTP_``. The above line would send the header named
``REMOTE_USER`` to gunicorn, and the WSGI application would receive it as ``HTTP_REMOTE_USER``. The
default configuration of Pulp is expecting ``REMOTE_USER`` in the WSGI environment not
``HTTP_REMOTE_USER``, so this won't work.

Pulp provides a setting named `REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>`_ which allows
you to specify another WSGI environment variable to read the authenticated username from.

.. warning::

    Configuring this has serious security implications. See the `Django warning at the end of this
    section in their docs <https://docs.djangoproject.com/en/2.2/howto/auth-remote-user/
    #configuration>`_ for more details.


Disabling Webserver Auth
************************

To disable Pulp from using webserver authentication remove the
``'django.contrib.auth.backends.RemoteUserBackend'`` from the ``AUTHENTICATION_BACKENDS`` setting in
Pulp.

You can configure Django Rest Framework to not trust webserver authenticated users by removing
``'rest_framework.authentication.RemoteUserAuthentication'`` from the
``REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']`` .


Custom Authentication
---------------------

Pulp is a Django app, so additional Django authentication can be added as long as it's correctly
configured for both Django and Django Rest Frameowork.

See the `Django docs on configuring custom authentication <https://docs.djangoproject.com/en/2.2/
topics/auth/customizing/#customizing-authentication-in-django>`_ and the `Django Rest Framework docs
on configuring custom authentication <https://www.django-rest-framework.org/api-guide/authentication
/#custom-authentication>`_.
