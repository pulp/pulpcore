Installation Instructions
=========================

Supported Platforms
-------------------

Pulp should work on any operating system that can provide a Python 3.6+ runtime environment and
the supporting dependencies e.g. a database. Pulp has been demonstrated to work on Ubuntu, Debian,
Fedora, CentOS, and Mac OSX.

.. note::

    Pulp 3 currently does not have an SELinux Policy or AppArmor Profile. Until then, any
    environment you run Pulp3 in needs have have SELinux or AppArmor either permissive or disabled.
    There are risks associated with this decision. See your distribution's docs for more details

    To help resolve this situation see these tickets to get involved:

    `Run Pulp3 with SELinux Enforcing <https://pulp.plan.io/issues/3809>`_.
    `Enabling SELinux in pulplift <https://pulp.plan.io/issues/97>`_.


Ansible Installation (Recommended)
----------------------------------

To use ansible roles to install Pulp 3 instead of manual setup refer to
`Pulp 3 Ansible installer <https://github.com/pulp/ansible-pulp/>`_.

PyPI Installation
-----------------

1. (Optional) Create a user account & group for Pulp 3 to run under, rather than using root. The following values are recommended:

   * name: pulp
   * shell: The path to the `nologin` executable
   * home: ``MEDIA_ROOT``
   * system account: yes
   * create corresponding private group: yes

2. Install python3.6(+) and pip.

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


5. Follow the :ref:`configuration instructions <configuration>` to set ``SECRET_KEY`` and
   ``CONTENT_ORIGIN``.

6. Create the ``MEDIA_ROOT`` & ``WORKING_DIRECTORY`` with the prescribed permissions from the
   :ref:`configuration instructions. <configuration>`

7. Go through the :ref:`database-install`, :ref:`redis-install`, and :ref:`systemd-setup` sections

.. note::

    In place of using the systemd unit files provided in the `systemd-setup` section, you can run
    the commands yourself inside of a shell. This is fine for development but not recommended in production::

    $ /path/to/python/bin/rq worker -n 'resource-manager@%h' -w 'pulpcore.tasking.worker.PulpWorker' -c 'pulpcore.rqconfig'
    $ /path/to/python/bin/rq worker -w 'pulpcore.tasking.worker.PulpWorker' -c 'pulpcore.rqconfig'
    $ /path/to/python/bin/rq worker -w 'pulpcore.tasking.worker.PulpWorker' -c 'pulpcore.rqconfig'

8. Run Django Migrations::

   $ django-admin migrate --noinput
   $ django-admin reset-admin-password --password admin

9. Collect Static Media for live docs and browsable API::

   $ django-admin collectstatic --noinput

10. Run Pulp::

    $ pulp-content  # The Pulp Content service (listening on port 24816)
    $ django-admin runserver 24817  # The Pulp API service

.. _database-install:

Database Setup
--------------

You must provide a PostgreSQL database for Pulp to use. At this time, Pulp 3.0 will only work with
PostgreSQL.

PostgreSQL
^^^^^^^^^^

To install PostgreSQL, refer to the package manager or the
`PostgreSQL install docs <http://postgresguide.com/setup/install.html>`_. Oftentimes you can also find better
installation instructions for your particular operating system from third-parties such as Digital Ocean.

On Ubuntu and Debian, the package to install is named ``postgresql``. On Fedora and CentOS, the package
is named ``postgresql-server``.

The default PostgreSQL user and database name in the provided server.yaml file is ``pulp``. Unless you plan to
customize the configuration of your Pulp installation, you will need to create this user with the proper permissions
and also create the ``pulp`` database owned by the ``pulp`` user. If you do choose to customize your installation,
the database options can be configured in the `DATABASES` section of your server.yaml settings file.
See the `Django database settings documentation <https://docs.djangoproject.com/en/1.11/ref/settings/#databases>`_
for more information on setting the `DATABASES` values in server.yaml.

After installing and configuring PostgreSQL, you should configure it to start at boot, and then start it::

   $ sudo systemctl enable postgresql
   $ sudo systemctl start postgresql

.. _redis-install:

Redis
-----

The Pulp tasking system runs on top of Redis. This can be on a different host or the same host that
Pulp is running on.

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
`Pulp 3 Ansible Installer <https://github.com/pulp/ansible-pulp/>`_ makes these for you, but you
can also configure them by hand from the templates below. Custom configuration can be applied using
the ``Environment`` option with various :ref:`Pulp settings <configuration>`.


1. Make a ``pulpcore-content.service`` file for the pulpcore-content service which serves Pulp
   content to clients. We recommend starting with the `pulpcore-content template <https://github.com
   /pulp/ansible-pulp/blob/master/roles/pulp-content/templates/pulpcore-content.service.j2>`_ and
   setting the variables according to the `pulpcore-content config variables documentation <https://
   github.com/pulp/ ansible-pulp/tree/master/roles/pulp-content#variables>`_

2. Make a ``pulpcore-api.service`` file for the pulpcore-api service which serves the Pulp REST API. We
   recommend starting with the `pulpcore-api template <https://github.com/pulp/ansible-pulp/blob/master/
   roles/pulp/templates/pulpcore-api.service.j2>`_ and setting the variables according to the `pulpcore-api
   config variables documentation <https://github.com/pulp/ ansible-pulp/tree/master/roles/
   pulp-content#variables>`_

3. Make a ``pulpcore-worker@.service`` file for the pulpcore-worker processes which allows you to manage
   one or more workers. We recommend starting with the `pulpcore-worker template <https://github.com/pulp/
   ansible-pulp/blob/master/roles/pulp-workers/templates/pulpcore-worker%40.service.j2>`_ and setting
   the variables according to the `pulp-worker config variables documentation <https://github.com/
   pulp/ansible-pulp/tree/master/roles/pulp-workers#configurable-variables>`_

4. Make a ``pulpcore-resource-manager.service`` file which can manage one pulpcore-resource-manager
   process. We recommend starting with the `pulpcore-resource-manager template <https://github.com/pulp/
   ansible-pulp/blob/master/roles/pulp-resource-manager/templates/pulpcore-resource-manager.service.
   j2>`_ and setting the variables according to the `pulpcore-resource-manager config variables
   documentation <https://github.com/pulp/ansible-pulp/tree/master/roles/pulp-resource-manager#
   configurable-variables>`_

These services can then be started by running::

    sudo systemctl start pulpcore-resource-manager
    sudo systemctl start pulpcore-content
    sudo systemctl start pulpcore-api
    sudo systemctl start pulpcore-worker@1
    sudo systemctl start pulpcore-worker@2

