Added ``get_objects_for_user`` to support queryset filtering by roles. 
Added hooks in ``AutoAddObjPermsMixin`` to support auto-assignment of roles.

Changed the lookup for creation hooks so hooks need to be registered in
``REGISTERED_CREATION_HOOKS`` on the model to be used. The signature for creation hooks that are
registered must match the exploded version of the dict parameters from the access policy.
Unregistered creation hooks are deprecated and support will be dropped in pulpcore 3.20.
