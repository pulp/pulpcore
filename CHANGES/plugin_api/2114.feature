Plugins now have to enable default queryset scoping by setting the ``queryset_scoping`` field on the
  AccessPolicy to ``{"function": "scope_queryset"}``.
Default queryset scoping behavior can be changed by supplying a new ``scope_queryset`` method.
Extra queryset scoping functions can be declared on plugin ViewSets and used by setting the
  AccessPolicy's ``queryset_scoping`` field.
