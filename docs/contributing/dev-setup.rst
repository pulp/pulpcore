.. _DevSetup:

Developer Setup
===============

To ease developer setup, we have `Pulplift
<https://pulp-installer.readthedocs.io/en/latest/pulplift/>`_ as part of the installer repository,
which is based on the `Forklift <https://github.com/theforeman/forklift>`_ project and utilizes
`Ansible <https://docs.ansible.com/ansible/index.html>`_ roles and playbooks to provide supported
`Vagrant <https://docs.vagrantup.com/>`_ boxes that are more consistent with the user experience.

.. _getsource:

Get the Source
--------------

It is assumed that any Pulp project repositories are cloned into one directory. As long as Ansible
has read and write permissions, it doesn't matter where your **development directory** is.

You will need ``pulp/pulpcore`` at a minimum::

    $ git clone https://github.com/pulp/pulpcore.git

Additionally, you will need at least one plugin.::

    $ git clone https://github.com/pulp/pulp_file.git

The current base branch on this repository is the master branch.

.. warning::

    It is important to ensure that your repositories are all checked out to compatible versions.
    Check the ``setup.py`` of each repo see the version it provides, and the versions it requires.


Installation
------------

We recommend using ``pulplift`` for developer installations. Follow the instructions in the
`installer documentation <https://pulp-installer.readthedocs.io/en/latest/pulplift/>`_.

It is also possible to use the `Ansible roles
<https://github.com/pulp/pulp_installer#pulp-3-ansible-installer>`_ directly, if you prefer not to
use Vagrant.
