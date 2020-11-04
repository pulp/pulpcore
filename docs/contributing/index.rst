Contributing
============

Contribution documentation generally assumes that the reader is familiar with
:doc:`Pulp basics</concepts>`. If you have problems, you can :ref:`contact us<community>`
or :doc:`file an issue</bugs-features>`.

Workflow
--------

1. Clone the GitHub repo.
2. Make a change.
3. Make sure all tests pass.
4. Add a file into CHANGES folder for user facing changes and CHANGES/plugin_api for plugin API
   changes.
5. Commit changes to own ``pulpcore`` clone.
6. :doc:`Record a demo <record-a-demo>` (1-3 minutes).
7. Make pull request from github page for your clone against master branch.


Fundamentals
------------

.. toctree::
   :maxdepth: 1

   dev-setup
   tests
   style-guide
   documentation
   git
   record-a-demo
   pull-request-walkthrough


Plugin Development
------------------

Developers interested in writing plugins should reference the `Pulp Plugin API
<../plugins/index.html>`_ documentation.


Reference
---------

.. toctree::
   :maxdepth: 1

   architecture/index
   platform-api/index


Suggesting Changes to the Pulp Development Process
--------------------------------------------------

Pulp is a community project, and major changes to the way Pulp is developed, such as the release
cycle, and style guide, can be suggested by submitting a :term:`PUP`, or, "Pulp Update Proposal".
All approved PUPs live in the `PUP repository <https://github.com/pulp/pups/>`_.

`PUP-1 <https://github.com/pulp/pups/blob/master/pup-0001.md>`_ defines the PUP process itself.

All approved, rejected, and abandoned PUPs are tracked in the `PUP index
<https://github.com/pulp/pups/blob/master/README.md>`_
