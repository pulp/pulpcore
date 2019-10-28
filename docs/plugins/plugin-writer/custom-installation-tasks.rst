Custom Installation Tasks
=========================

If your plugin requires any custom installation steps, we recommend using an
Ansible Role prior to Pulp installation.

The easiest way to add custom installation tasks is to follow the
`Ansible Galaxy guide <https://galaxy.ansible.com/docs/contributing/creating_role.html>`_
to create a new role with tasks that needs to be done and publish it on Ansible Galaxy.

Documentation will need to be added to the plugin installation instructions. See the
`RPM Plugin Documentation <https://pulp-rpm.readthedocs.io/en/latest/installation.html#install-with-ansible-pulp>`_
as an example.