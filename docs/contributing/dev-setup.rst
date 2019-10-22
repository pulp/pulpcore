.. _DevSetup:

Developer Setup
===============

To ease developer setup, we have `Pulplift <https://github.com/pulp/pulplift>`_ which is based on
the `Forklift <https://github.com/theforeman/forklift>`_ project and utilizes
`Ansible <https://docs.ansible.com/ansible/index.html>`_ roles and playbooks to provide supported
`Vagrant <https://docs.vagrantup.com/>`_ boxes that are more consistent with the user experience.

.. _getsource:

Get the Source
--------------

It is assumed that any Pulp project repositories are cloned into one directory. As long as Ansible
has read and write permissions, it doesn't matter where your **development directory** is.

You will need ``pulp/pulpcore`` at a minimum::

    $ git clone https://github.com/pulp/pulpcore.git

This repository is for Pulp 3 only, development is done agains the master branch of
each.

Additionally, you will need at least one plugin.::

    $ git clone https://github.com/pulp/pulp_file.git

The current base branch on this repository is the master branch.

.. warning::

    It is important to ensure that your repositories are all checked out to compatible versions.
    Check the ``setup.py`` of each repo see the version it provides, and the versions it requires.


Installation
------------

We recommened using ``pulplift`` for developer installations. Follow the instructions in the
`README.md <https://github.com/pulp/pulplift/#pulplift>`_.

It is also possible to use the `Ansible roles
<https://github.com/pulp/ansible-pulp#pulp-3-ansible-installer>`_ directly, if you prefer not to
use Vagrant.
