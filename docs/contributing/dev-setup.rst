.. _DevSetup:

Developer Setup
===============

To ease developer setup, we have the `oci-env <https://github.com/pulp/oci_env>`_ which is our
developer environment based off the `Pulp OCI Images <https://github.com/pulp/pulp-oci-images>`_.
It is a CLI tool that uses ``docker/podman-compose`` to quickly setup a Pulp instance with your
specified configuration.

.. _getsource:

Get the Source
--------------

It is assumed that any Pulp project repositories are cloned into one directory. You must clone the
``oci-env`` into the same directory as all of your other Pulp project repositories.::

    $ git clone https://github.com/pulp/oci_env.git

You will need ``pulp/pulpcore`` at a minimum::

    $ git clone https://github.com/pulp/pulpcore.git

Additionally, you will need at least one plugin.::

    $ git clone https://github.com/pulp/pulp_file.git

The current base branch on this repository is the main branch.

.. warning::

    It is important to ensure that your repositories are all checked out to compatible versions.
    Check the ``setup.py`` and ``requirements.txt`` files of each repository to see what version
    it provides and which versions it requires, respectively.


Installation
------------

Follow the steps at `Getting Started <https://github.com/pulp/oci_env/#getting-started>`_ to setup
your Pulp instance after cloning the Pulp repositories.
