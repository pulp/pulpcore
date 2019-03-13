.. _getsource:

Get the Source
==============

It is assumed that any Pulp project repositories are cloned into one directory. As long as Ansible has read and write permissions, it doesn't matter where your **development directory** is.

.. note::

    The git repositories required by each role are documented in :ref:`ansible-roles`.

You will need ``pulp/devel`` and ``pulp/pulpcore`` at a minimum::

    $ git clone https://github.com/pulp/devel.git
    $ git clone https://github.com/pulp/pulpcore.git

If you want to use the ``plugin`` role, you'll need to clone the corresponding plugin repository.::

    $ git clone https://github.com/pulp/pulp_file.git

The current base branch on this repository is the master branch.

If your playbook includes optional :ref:`ansible-roles`, you may require additional repositories::

    $ git clone https://github.com/PulpQE/pulp-smash.git
    $ git clone https://github.com/pulp/pulpproject.org.git


.. warning::

    It is important to ensure that your repositories are all checked out to compatible versions.
