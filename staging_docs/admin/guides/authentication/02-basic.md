# Authenticate using basic credentials

Pulp by default uses [Basic Authentication](https://tools.ietf.org/html/rfc7617) which checks the
user submitted header against an internal database of users. If the username and password match, the
request is considered authenticated as that username. Basic auth transmits credentials as
user-id and password joined with a colon and then encoded using Base64. This is passed along as the
`Authorization` header.

Below is an example of a Basic Authentication header for a username `admin` and password
`password`.:

```
Authorization: Basic YWRtaW46cGFzc3dvcmQ=
```

You can set this header on a [httpie](https://httpie.org/) command using the `--auth` option:

```
http --auth admin:password ...
```

You could also specify the header manually on a [httpie](https://httpie.org/) command using its
header syntax:

```
http Authorization:"Basic YWRtaW46cGFzc3dvcmQ=" ...
```

!!! warning
    For the 3.y releases, Pulp expects the user table to have exactly 1 user in it named 'admin',
    which is created automatically when the initial migration is applied. The password for this user
    can be set with the `pulpcore-manager reset-admin-password` command.
    To articulate what you'd like to see future versions of Pulp file a feature request
    [here](https://github.com/pulp/pulpcore/issues) or reach out via
    [pulp-list@redhat.com](https://www.redhat.com/mailman/listinfo/pulp-list).


## Disabling Basic Authentication

Basic Authentication is defined by receiving the username and password encoded in the
`Authorization` header. To disable receiving the username and password using Basic Authentication,
remove the `rest_framework.authentication.BasicAuthentication` from the
`REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']` list.
