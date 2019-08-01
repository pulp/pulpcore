3.0.0rc2
========

`Comprehensive list of changes and bugfixes for rc 2 <https://github.com/pulp/pulpcore/compare/3.0.0rc1...3.0.0rc2>`_.

Breaking Changes
----------------

Default port changes happened in the `Ansible Installer for Pulp <https://github.com/pulp/
ansible-pulp>`_ and pulpcore was updated to match with `this PR <https://github.com/pulp/pulpcore/
pull/75>`_. Existing installs are unaffected. This was done to avoid conflicts that would prevent
Pulp from starting by default in many environments; the previous ports (8000 & 8080) are commonly
used by management webGUIs, development webservers, etc.

Publications are now Master/Detail which causes any Publication URL endpoint to change. To give an
example from `pulp_file <https://github.com/pulp/pulp_file>`_ see the URL changes made
`here <https://github.com/pulp/pulp_file/pull/205/files#diff-88b99bb28683bd5b7e3a204826ead112R200>`_
as an example. See plugin docs compatible with 3.0.0rc2 for more details.

Distributions are now Master/Detail which causes the Distribution URL endpoint to change. To give an
example from `pulp_file <https://github.com/pulp/pulp_file>`_ see the URL changes made
`in this PR <https://github.com/pulp/pulp_file/pull/219/files>`_ as an example. See plugin docs
compatible with 3.0.0rc2 for more details.

The semantics of :term:`Remote` attributes ``ssl_ca_certificate``, ``ssl_client_certificate``, and
``ssl_client_key`` changed even though the field names didn't. Now these assets are saved directly
in the database instead of on the filesystem, and they are prevented from being read back out to
users after being set for security reasons. This was done with `these changes <https://github.com/
pulp/pulpcore/pull/99/>`_.

3.0.0rc1
========

`Comprehensive list of changes and bugfixes for rc 1 <https://github.com/pulp/pulpcore/compare/3.0.0b23...3.0.0rc1>`_.
