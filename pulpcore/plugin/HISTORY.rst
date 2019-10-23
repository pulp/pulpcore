0.1.0rc2
========

* `List of plugin API related changes in rc 2 <https://github.com/pulp/pulpcore-plugin/compare/0.1.0rc1...0.1.0rc2>`_

Breaking Changes
----------------

`The RepositoryPublishURLSerializer was removed from the plugin API. <https://github.com/pulp/
pulpcore-plugin/pull/93/>`_

`Distributions are now Master/Detail. <https://pulp.plan.io/issues/4785>`_ All plugins will require
updating to provide a detail Distribution. Here is an example of pulp_file introducing the
`FileDistribution <https://github.com/pulp/pulp_file/pull/217>`_ as an example of changes to match.

`Publications are now Master/Detail. <https://pulp.plan.io/issues/4678>`_ Plugins that use
Publications will need to provide a detail Publication. Here is an example of pulp_file introducing
the `FilePublisher <https://github.com/pulp/pulp_file/pull/205>`_ as an example of changes to match
along with its `follow-on change <https://github.com/pulp/pulp_file/pull/215>`_.

0.1.0rc1
========

* `List of plugin API related changes in rc 1 <https://github.com/pulp/pulpcore-plugin/compare/0.1.0b21...0.1.0rc1>`_
