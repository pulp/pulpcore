Contributing
============

Contribution documentation generally assumes that the reader is familiar with
:doc:`Pulp basics</concepts>`. If you have problems, you can :ref:`contact us<community>`
or :doc:`file an issue</bugs-features>`.

Workflow
--------

1. Clone the GitHub repo
2. Make a change
3. Make sure all tests passed
4. Add a file into CHANGES folder (Changelog update).
5. Commit changes to own ``pulpcore`` clone
6. Make pull request from github page for your clone against master branch


Fundamentals
------------

.. toctree::
   :maxdepth: 1

   dev-setup
   runtests
   style-guide
   pull-request-walkthrough


Plugin Development
------------------

Developers interested in writing plugins should reference the `Pulp Plugin API
<../../../pulpcore-plugin/nightly/>`_ documentation.


Reference
---------

.. toctree::
   :maxdepth: 1

   architecture/index
   error-handling
   platform-api/index
   git
   continuous-integration
   documentation
   pups
   build-guide
