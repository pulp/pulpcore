Added a role model to support RBAC and the utility functions ``assign_role`` and ``remove_role``.

The field ``permissions_assignment`` of access policies has been renamed to ``creation_hooks``. A
compatibility patch has been added to be removed with pulpcore=3.20.

The ``permissions`` argument to ``creation_hooks`` has been deprecated to be removed with
pulpcore=3.20.
