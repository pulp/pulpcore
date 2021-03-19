Added the following new objects related to a new ``Distribution`` MasterModel:
* ``pulpcore.plugin.models.Distribution`` - A new MasterModel ``Distribution`` which replaces the
  ``pulpcore.plugin.models.BaseDistribution``. This now contains the ``repository``,
  ``repository_version``, and ``publication`` fields on the MasterModel instead of on the detail
  models as was done with ``pulpcore.plugin.models.BaseDistribution``.
* ``pulpcore.plugin.serializer.DistributionSerializer`` - A serializer plugin writers should use
  with the new ``pulpcore.plugin.models.Distribution``.
* ``pulpcore.plugin.viewset.DistributionViewSet`` - The viewset that replaces the deprecated
  ``pulpcore.plugin.viewset.BaseDistributionViewSet``.
* ``pulpcore.plugin.viewset.NewDistributionFilter`` - The filter that pairs with the
  ``Distribution`` model.
