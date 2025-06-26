# Content Protection

By default, the Content app will serve all content, but some deployments want to only serve content to some users and not others.
For example `pulp_rpm` wants to only give rpms in certain repositories to users with a valid certificate declaring their paid access to content.
To allow fine-grained customization of how content is protected, a plugin writer can define a `ContentGuard`.

## Defining a ContentGuard

The [`ContentGuard`][ContentGuard] is a Master/Detail object.

In your plugin code, subclass `ContentGuard` and optionally add additional fields as necessary to define how authentication and authorization are to be performed.
Then overwrite the `permit` method so that it returns `None` if access is granted and throws a `PermissionError` on denial.
As with all [Master/Detail] objects a `TYPE` class attribute is needed which is then used to construct the URL:

```
/pulp/api/v3/contentguards/<plugin_name>/<TYPE>/
```

!!! note
    The [`pulp-certguard`][pulp-certguard] plugin ships various `ContentGuard` types for client-certificate-based authentication.
    Plugins can ship their own content guards too, but look at the existing ones first.


### Toy Example

Here's a trivial example where the client needs to send a header named `SECRET_STRING`.
If its value matches a recorded value for that ContentGuard instance, access to the content is granted.
The secret both authenticates the user and authorizes them for this Content.

#### Implementing the ContentGuard

```python
# in pulp_my_plugin/app/models.py

from pulpcore.plugin.models import EncryptedTextField, ContentGuard

class SecretStringContentGuard(ContentGuard):

    TYPE = 'secret_string'

    secret_string = EncryptedTextField(max_length=255)

    def permit(self, request):
        """

        Authorize the specified web request.

        Args:
            request (aiohttp.web.Request): A request for a published file.

        Raises:
            PermissionError: When the request cannot be authorized.
        """
        provided_string = request.headers.get("SECRET_STRING")
        if provided_string != self.secret_string:
            raise PermissionError("Welcome to the real world!")

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
```

#### Adding Serializers and Views

In order to make the `ContentGuard` accessible via the api, you need to create a [serializer] and a [viewset] in the usual manner.

#### Using the ContentGuard

Users create an instance of a `SecretStringContentGuard` and give it a secret string with `httpie`:

```
http POST http://localhost:24817/pulp/api/v3/contentguards/my_plugin/secret_string/ \
              secret_string='2xlSFgJwOhbLrtIlmYszqHQy7ivzdQo9'
```

Then the user can protect one or more distributions by specifying its `content_guard`.
See the [Distribution API] for more information.


## Plugin Internal use of Content Guards

Plugin writers can also programatically create detail `ContentGuard` instances and/or have the plugin's detail distribution define its use.
This allows plugin writers to offer content protection features specific to certain package ecosystems.

[ContentGuard]: pulpcore.plugin.models.ContentGuard
[Distribution API]: site:pulpcore/restapi/#tag/Distributions:-File/operation/distributions_file_file_list
[Master/Detail]: site:pulpcore/docs/dev/learn/plugin-concepts#masterdetail-models
[pulp-certguard]: site:pulp_certguard
[serializer]: site:pulpcore/docs/dev/learn/subclassing/serializers
[viewset]: site:pulpcore/docs/dev/learn/subclassing/viewsets
