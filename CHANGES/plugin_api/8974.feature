The settings file switched ``DEFAULT_PERMISSION_CLASSES`` to use ``AccessPolicyFromDB`` instead of
``IsAdminUser`` with a fallback to a behavior of ``IsAdminUser``. With this feature plugin writers
no longer need to declare ``permission_classes`` on their Views or Viewsets to use
``AccessPolicyFromDB``.
