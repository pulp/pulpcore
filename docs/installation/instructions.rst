Instructions
============

Supported Platforms
-------------------

Pulp should work on any operating system that can provide a Python 3.8+ runtime environment and
the supporting dependencies e.g. a database. Pulp has been demonstrated to work on Ubuntu, Debian,
Fedora, CentOS, and Mac OSX.

.. note::

    Pulp 3 currently does not have an AppArmor Profile. Until then, any
    environment you run Pulp 3 in must have AppArmor either permissive or disabled.
    There are risks associated with this decision. See your distribution's docs for more details


Ansible Installation (Recommended)
----------------------------------

The Pulp 3 Ansible Installer is a collection of Ansible roles designed to automate the installation of Pulp and any content plugins that you want.

You can customize and configure your Pulp deployment through the Ansible variables for each role.

For comprehensive and up-to-date instructions about using the Pulp Ansible installer, see the
`Pulp Installer documentation <https://docs.pulpproject.org/pulp_installer/>`__.


PyPI Installation
-----------------

1. (Optional) Create a user account & group for Pulp 3 to run under, rather than using root. The following values are recommended:

   * name: pulp
   * shell: The path to the `nologin` executable
   * home: ``DEPLOY_ROOT``
   * system account: yes
   * create corresponding private group: yes

2. Install python3.8(+) and pip.

3. Create a pulp venv::

   $ python3 -m venv pulpvenv
   $ source pulpvenv/bin/activate

.. note::

   On some operating systems you may need to install a package which provides the ``venv`` module.
   For example, on Ubuntu or Debian you need to run::

   $ sudo apt-get install python3-venv

4. Install Pulp using pip::

   $ pip install pulpcore

.. note::

   To install from source, clone git repositories and do a local, editable pip installation::

   $ git clone https://github.com/pulp/pulpcore.git
   $ pip install -e ./pulpcore[postgres]

5. Configure Pulp by following the :ref:`configuration instructions <configuration>`.

6. Set ``SECRET_KEY`` and ``CONTENT_ORIGIN`` according to the :ref:`settings <settings>`.

7. Create ``MEDIA_ROOT`` and ``WORKING_DIRECTORY`` with the prescribed permissions proposed in
   the :ref:`settings <settings>`.

8. Go through the :ref:`database-install`, :ref:`redis-install`, and :ref:`systemd-setup` sections.

9. Run Django Migrations::

   $ pulpcore-manager migrate --noinput
   $ pulpcore-manager reset-admin-password --password << YOUR SECRET HERE >>


.. note::

    The ``pulpcore-manager`` command is ``manage.py`` configured with the
    ``DJANGO_SETTINGS_MODULE="pulpcore.app.settings"``. You can use it anywhere you would normally
    use ``manage.py``.

.. warning::

    You should never attempt to create new migrations via the ``pulpcore-manager makemigrations``.
    In case, new migrations would be needed, please file a bug against the respective plugin.
    :ref:`issue-writing`

.. note::

    In place of using the systemd unit files provided in the `systemd-setup` section, you can run
    the commands yourself inside of a shell. This is fine for development but not recommended in production::

    $ /path/to/python/bin/pulpcore-worker --resource-manager
    $ /path/to/python/bin/pulpcore-worker

10. Collect Static Media for live docs and browsable API::

    $ pulpcore-manager collectstatic --noinput

11. Run Pulp::

    $ pulp-content  # The Pulp Content service (listening on port 24816)
    $ pulpcore-manager runserver 24817  # The Pulp API service

.. _database-install:

Database Setup
--------------

You must provide a PostgreSQL database for Pulp to use. At this time, Pulp 3.0 will only work with
PostgreSQL.

PostgreSQL
^^^^^^^^^^

Installation package considerations
***********************************

To install PostgreSQL, refer to the package manager or the
`PostgreSQL install docs <http://postgresguide.com/setup/install.html>`_. Oftentimes, you can also find better
installation instructions for your particular operating system from third-parties such as Digital Ocean.

On Ubuntu and Debian, the package to install is named ``postgresql``. On Fedora and CentOS, the package
is named ``postgresql-server``.

User and database configuration
*******************************

The default PostgreSQL user and database name in the provided server.yaml file is ``pulp``. Unless you plan to
customize the configuration of your Pulp installation, you will need to create this user with the proper permissions
and also create the ``pulp`` database owned by the ``pulp`` user. If you do choose to customize your installation,
the database options can be configured in the `DATABASES` section of your server.yaml settings file.
See the `Django database settings documentation <https://docs.djangoproject.com/en/2.2/ref/settings/#databases>`_
for more information on setting the `DATABASES` values in server.yaml.

UTF-8 encoding
**************

You must configure PostgreSQL to use UTF-8 character set encoding.

Post-installation setup
***********************

After installing and configuring PostgreSQL, you should configure it to start at boot, and then start it::

   $ sudo systemctl enable postgresql
   $ sudo systemctl start postgresql

.. _redis-install:

Redis
-----

Pulp can use Redis to cache requests to the content app. This can be installed on a different host
or the same host that Pulp is running on.

To install Redis, refer to your package manager or the
`Redis download docs <https://redis.io/download>`_.

For Fedora, CentOS, Debian, and Ubuntu, the package to install is named ``redis``.

After installing and configuring Redis, you should configure it to start at boot and start it::

   $ sudo systemctl enable redis
   $ sudo systemctl start redis

.. _systemd-setup:

Systemd
-------

To run the four Pulp services, systemd files needs to be created in /usr/lib/systemd/system/. The
`Pulp 3 Ansible Installer <https://docs.pulpproject.org/pulp_installer/>`__ makes these for you, but you
can also configure them by hand from the templates below. Custom configuration can be applied using
the ``Environment`` option with various :ref:`Pulp settings <settings>`.


1. Make a ``pulpcore-content.service`` file for the pulpcore-content service which serves Pulp
   content to clients. We recommend starting with the `pulpcore-content template <https://github.com
   /pulp/pulp_installer/blob/master/roles/pulp_content/templates/pulpcore-content.service.j2>`_ and
   setting the variables according to the `pulpcore_content config variables documentation <https://
   github.com/pulp/ pulp_installer/tree/master/roles/pulp_content#role-variables>`_

2. Make a ``pulpcore-api.service`` file for the pulpcore-api service which serves the Pulp REST API. We
   recommend starting with the `pulpcore-api template <https://github.com/pulp/pulp_installer/blob/master/roles/pulp_api/templates/pulpcore-api.service.j2>`_
   and setting the variables according to the `pulpcore-api config variables documentation <https://github.com/pulp/pulp_installer/tree/master/roles/pulp_api#role-variables>`_

3. Make a ``pulpcore-worker@.service`` file for the pulpcore-worker processes which allows you to manage
   one or more workers. We recommend starting with the `pulpcore-worker template <https://github.com/pulp/
   pulp_installer/blob/master/roles/pulp_workers/templates/pulpcore-worker%40.service.j2>`_ and setting
   the variables according to the `pulp_workers config variables documentation <https://github.com/
   pulp/pulp_installer/tree/master/roles/pulp_workers#role-variables>`_

4. Make a ``pulpcore-resource-manager.service`` file which can manage one pulpcore-resource-manager
   process. We recommend starting with the `pulpcore-resource-manager template <https://github.com/pulp/
   pulp_installer/blob/master/roles/pulp_resource_manager/templates/pulpcore-resource-manager.service.
   j2>`_ and setting the variables according to the `pulp_resource_manager config variables
   documentation <https://github.com/pulp/pulp_installer/tree/master/roles/pulp_resource_manager#role-variables>`_

These services can then be started by running::

    sudo systemctl start pulpcore-resource-manager
    sudo systemctl start pulpcore-content
    sudo systemctl start pulpcore-api
    sudo systemctl start pulpcore-worker@1
    sudo systemctl start pulpcore-worker@2

.. _ssl-setup:

SSL
---

Users should configure HTTPS communication between clients and the reverse proxy that is in front of pulp services
like pulpcore-api and pulpcore-content. The Pulp Installer provides three different options for configuring SSL
certificates for nginx and httpd reverse proxies.

1. By default, the installer will generate a new Certificate Authority and use it to sign an SSL certificate. In
   this case, the Pulp administrator will need to distribute the Certificate Authority certificate or the SSL
   certificate to all clients that wish to communicate with Pulp. Clients will need to import one of these
   certificates to their system CA trust store.

   The default location for the CA certificate is ``/etc/pulp/certs/root.crt``. The default location for the SSL
   certificate is ``/etc/pulp/certs/pulp_webserver.crt``.

2. If you already have an SSL Cerificate that you want to be used by the reverse proxy to encrypt communication
   with clients, the Pulp Installer supports providing a path for ``pulp_webserver_tls_cert`` and
   ``pulp_webserver_tls_key``. The administrator is still responsible for making sure that clients trust the
   Certificate Authority that signed the SSL certificate.

3. The Pulp Installer also supports using services that use the ACME protocol, e.g. https://letsencrypt.org/,  to
   generate trusted SSL certificates. See the Pulp Installer documentation for `instructions and an example playbook
   <https://docs.pulpproject.org/pulp_installer/letsencrypt/>`_.
