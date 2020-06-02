A new `pulpcore.plugin.models.AutoDeleteObjPermsMixin` object can be added to models to
automatically delete all user and group permissions for an object just before the object is deleted.
This provides an easy cleanup mechanism and can be added to models as a mixin. Note that your model
must support `django-lifecycle` to use this mixin.
