.. _authentication-overview:

Overview
--------

By default, Pulp supports Basic and Session authentication. The Basic Authentication checks the
username and password against the internal users database.

.. note::
    This authentication is only for the REST API. Client's fetching binary data have their identity
    verified and authorization checked using a :term:`ContentGuard`.


Which URLs Require Authentication?
**********************************

All URLs in the REST API require authentication except the Status API, ``/pulp/api/v3/status/``,
which is served to unauthenticated users too. This is true regardless of the type of authentication
you configure.


Concepts
********

Authentication in Pulp is provided by Django Rest Framework and Django together.

Django provides the
`AUTHENTICATION_BACKENDS <https://docs.djangoproject.com/en/2.2/ref/settings/#std:setting-AUTHENTICATION_BACKENDS>`_
which defines a set of behaviors to check usernames and passwords against.

Django Rest Framework defines the source usernames and passwords come from with the
`DEFAULT_AUTHENTICATION_CLASSES <https://www.django-rest-framework.org/api-guide/authentication/#setting-the-authentication-scheme>`_
setting.
