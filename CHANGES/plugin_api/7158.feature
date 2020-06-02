A new model `pulpcore.plugin.models.AccessPolicy` is available to store AccessPolicy statements in
the database. The model's `statements` field stores the list of policy statements as a JSON field.
The `name` field stores the name of the Viewset the `AccessPolicy` is protecting.

Additionally, the `pulpcore.plugin.access_policy.AccessPolicyFromDB` is a drf-access-policy which
viewsets can use to protect their viewsets with. See the :ref:`viewset_enforcement` for more
information on this.
