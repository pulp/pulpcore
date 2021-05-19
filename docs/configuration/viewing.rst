.. viewing-settings:

Viewing Settings
================

To list the effective settings on a Pulp installation, while on the system where Pulp is installed
run the command ``dynaconf list``. This will show the effective settings Pulp will use.

Note that settings can come from both settings file and environment variables, so when running the
``dynaconf list`` command be sure you have the same environment variables set as your Pulp
installation.
