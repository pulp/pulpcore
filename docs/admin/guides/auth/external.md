# Authenticate using external service

Pulp can be configured to use authentication provided in the webserver outside of Pulp. This allows
for integration with ldap for example, through [mod_ldap](https://httpd.apache.org/docs/2.4/mod/mod_ldap.html), or certificate based API access, etc.

## Enable external Auth

### 1. Accept external Auth

Accept external auth instead of checking the internal users database by setting the
`AUTHENTICATION_BACKENDS` to `['django.contrib.auth.backends.RemoteUserBackend']`.

This will cause Pulp to accept any username for each request and by default create a user in the database
backend for them. To have any name accepted but not create the user in the database backend, use the
`pulpcore.app.authentication.PulpNoCreateRemoteUserBackend` instead.

It is preferable to have users created because the authorization and permissions continue to
function normally since there are users in the Django database to assign permissions to and later
check. When using the `pulpcore.app.authentication.PulpNoCreateRemoteUserBackend` you also should
set the `DEFAULT_PERMISSION_CLASSES` to check permissions differently or not at all. By default
Pulp sets `DEFAULT_PERMISSION_CLASSES` to `pulpcore.plugin.access_policy.AccessPolicyFromDB`
which provides role based permission checking via a user in the database. For example, to only serve
to authenticated users specify set `DEFAULT_PERMISSION_CLASSES` to
`rest_framework.permissions.IsAuthenticated`. Alternatively, to allow any user (even
unauthenticated) use `rest_framework.permissions.AllowAny`.

### 2. Configure 

Specify how to receive the username from the webserver. Do this by specifying to DRF an
`DEFAULT_AUTHENTICATION_CLASSES`. For example, consider this example:

 ```python
 REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = (
     'rest_framework.authentication.SessionAuthentication',
     'pulpcore.app.authentication.PulpRemoteUserAuthentication'
 )
 ```

This removes `rest_framework.authentication.BasicAuthentication`, but retains
`rest_framework.authentication.SessionAuthentication` and adds
`PulpRemoteUserAuthentication`. This accepts the username as WSGI environment variable
`REMOTE_USER` by default, but can be configured via the
`REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>` Pulp setting.



## Webserver Auth in Same Webserver

If your webserver authentication is occurring in the same webserver that is serving the
`pulpcore.app.wsgi` application, you can pass the authenticated username to Pulp via the WSGI
environment variable `REMOTE_USER`.

Reading the `REMOTE_USER` WSGI environment is the default behavior of the
`rest_framework.authentication.RemoteUserAuthentication` and the Pulp provided
`pulpcore.app.authentication.PulpRemoteUserAuthentication`. The only difference in the Pulp
provided one is that the WSGI environment variable name can be configured.

See the `REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>` for configuring the WSGI provided
name, but if you are using the `REMOTE_USER` WSGI environment name with "same webserver"
authentication, you likely want to leave `REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>`
unset and configure the webserver to set the `REMOTE_USER` WSGI environment variable.



## Webserver Auth with Reverse Proxy

For example purposes, assume you're using Nginx with LDAP authentication required and after
authenticating it reverse proxies your request to the gunicorn process running the pulpcore.app.wsgi
application. That would look like this:

```
nginx <---http---> gunicorn <----WSGI----> pulpcore.app.wsgi application
```

With nginx providing authentication, all it can do is pass `REMOTE-USER` (or similar name) to the
application webserver, i.e. gunicorn. You can pass the header as part of the proxy request in nginx
with a config line like:

```
proxy_set_header REMOTE-USER $remote_user;
```

Per the [WSGI standard](https://www.python.org/dev/peps/pep-0333/#environ-variables),
any incoming headers will be prepended with a `HTTP_`. The above line would send
the header named `REMOTE-USER` to gunicorn, and the WSGI application would receive
it as `HTTP_REMOTE_USER` (after gunicorn normalization). The default configuration
of Pulp is expecting `REMOTE_USER` in the WSGI environment not `HTTP_REMOTE_USER`,
so this won't work with `pulpcore.app.authentication.PulpRemoteUserAuthentication`
or the Django Rest Framework provided `rest_framework.authentication.RemoteUserAuthentication` as is.

Pulp provides a setting named `REMOTE_USER_ENVIRON_NAME <remote-user-environ-name>` which allows
you to specify another WSGI environment variable to read the authenticated username from.

!!! warning
    Configuring this has serious security implications. See the [Django warning at the end of this
    section in their docs](https://docs.djangoproject.com/en/4.2/howto/auth-remote-user/#configuration) for more details.

