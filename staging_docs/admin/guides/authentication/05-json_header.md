# JSON Header Authentication

In a situation where it is not possible to use `Basic Authentication` Pulp can rely on a third-party
service to authenticate a user.
Using `JSONHeaderRemoteAuthentication` it's possible to receive a payload and even use `JQ` to filter
it and obtain a user. The user is created in the database if one is not found.

You can set `AUTHENTICATION_JSON_HEADER` and `AUTHENTICATION_JSON_HEADER_JQ_FILTER` to obtain a user
given a header name and its value respectively::

```python title="settings.py"
AUTHENTICATION_JSON_HEADER = "HTTP_X_AUTHENTICATION_SERVICE"
AUTHENTICATION_JSON_HEADER_JQ_FILTER = ".identity.user.username"
```

will look for a `x-authentication-service` header and its content. With the given filter, it will
extract the information from a payload like this::
    
```json
{
  identity: {
    user: {
      username: "user"
    }
  }
}

```

## Enabling JSONHeaderRemoteAuthentication

The `JSONHeaderRemoteAuthentication` can be enabled by:

1. Add the `django.contrib.auth.backends.RemoteUserBackend` to
`AUTHENTICATION_BACKENDS`, or some authentication backend that subclasses it.

2. You need to add the `pulpcore.app.authentication.JSONHeaderRemoteAuthentication` to 
`REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']` setting.

3. Change the `AUTHENTICATION_JSON_HEADER` to your value of choice. Remember that it
must start with `HTTP_`, so, if your header is `x-authentication-service`, you need to set it to 
`HTTP_X_AUTHENTICATION_SERVICE`.

4. Set a JQ filter on `AUTHENTICATION_JSON_HEADER_JQ_FILTER`. You can find the JQ query syntax and reference on its
official site [here](https://jqlang.github.io/jq/).

Remember that the content of the header must be Base64 encoded.
