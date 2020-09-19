Releasing Your Plugin
=====================

Depending on pulpcore
---------------------

The Plugin API is not yet stable, but starting with pulpcore 3.7.0, a
:ref:`deprecation process <deprecation_policy>` is in place which makes it safe for a plugin
to declare compatability with the next, unreleased pulpcore version also. For example, a plugin
compatible with pulpcore 3.7 would declare compatibility up to pulpcore 3.8. In this example, use
the following requirements string::

    pulpcore>=3.7,<3.9

This ensures that when pulpcore 3.8 is released, users can receive it immediately and use it without
any issue. However when 3.9 comes out, any deprecations introduced in the ``pulpcore.plugin`` API in
3.8 will be removed, so preventing your plugin from working with pulpcore 3.9 maintains
compatibility.

Sometimes plugins can be compatible with older version of pulpcore, and in those cases the oldest
version should be allowed. For example if your plugin is compatible with pulpcore 3.5, and you just
tested it against 3.7 and it's still compatible, use this requirements string::


    pulpcore>=3.5,<3.9
