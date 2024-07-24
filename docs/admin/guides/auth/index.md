# Overview

By default, Pulp supports Basic and Session authentication. The Basic Authentication checks the
username and password against the internal users database.

!!! note
    This authentication is only for the REST API. Clients fetching binary data have their identity
    verified and authorization checked using a `ContentGuard`.


## Which URLs Require Authentication?

All URLs in the REST API require authentication except the Status API, `/pulp/api/v3/status/`.

## Concepts

Authentication in Pulp is provided by Django Rest Framework and Django together.

Django provides the [AUTHENTICATION_BACKENDS](https://docs.djangoproject.com/en/4.2/ref/settings/#std:setting-AUTHENTICATION_BACKENDS) which defines a set of behaviors to check usernames and
passwords against. By default it is set to:

```python
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',  # Django's users, groups, and permissions
    'pulpcore.backends.ObjectRolePermissionBackend'  # Pulp's RBAC object and model permissions
]
```

Django Rest Framework defines the source usernames and passwords come from with the
[DEFAULT_AUTHENTICATION_CLASSES](https://www.django-rest-framework.org/api-guide/authentication/#setting-the-authentication-scheme) setting. By default it is set to:

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',  # Session Auth
        'rest_framework.authentication.BasicAuthentication'  # Basic Auth
    ]
}
```

## Extend

Pulp is a Django app and Django Rest Framework (DRF) application, so additional authentication can
be added as long as it's correctly configured for both Django and Django Rest Frameowork.

See the [Django docs on configuring custom authentication](https://docs.djangoproject.com/en/4.2/topics/auth/customizing/#customizing-authentication-in-django) and the [Django Rest Framework docs
on configuring custom authentication](https://www.django-rest-framework.org/api-guide/authentication/#custom-authentication).
