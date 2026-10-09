# SAML2

!!! warning
    This is in feature-preview.

The saml2 authentication provider can pass the `pulp_roles` attribute alongside the authentication credentials.
In order to attach e.g. the `file_uploader` role scoped to the `default` domain to the user, the following attribute is needed:

`{"pulp_roles": ["file.file_uploader/default/"]}`

[djangosaml2]: https://djangosaml2.readthedocs.io
[pysaml2]: https://pysaml2.readthedocs.io
