A new `pulpcore.plugin.models.AutoAddObjPermsMixin` object can be added to models to automatically
add permissions for an object just after the object is created. This is controlled by data saved in
the `permissions_assignment` attribute of the `pulpcore.plugin.models.AccessPolicy` allowing users
to control what permissions are created. Note that your model must support `django-lifecycle` to use
this mixin.
