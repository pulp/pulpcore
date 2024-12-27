Added a check to the basic auth module to respect the `X-Requested-With: "XMLHttpRequest"` header.
In return the signature of the `WWW-Authenticate` header is changed so browsers will not pop up a password dialog.
