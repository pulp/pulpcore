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


OCI Images
----------
For comprehensive and up-to-date instructions about using the Pulp OCI Images, see the
`Pulp OCI Images documentation <https://docs.pulpproject.org/pulp_oci_images/>`__.

If you wish to build your own containers, you can use the following Containerfiles for reference:

The Containerfile used to build the `base` image is `here <https://github.com/pulp/pulp-oci-images/blob/latest/images/Containerfile.core.base>`__.

The Containerfile used to build the `pulp-minimal` image used to run a single Pulp service is `here <https://github.com/pulp/pulp-oci-images/blob/latest/images/pulp-minimal/stable/Containerfile.core>`__.

The Containerfile used to build the `pulp-web` (reverse proxy) image used to proxy requests to `pulpcore-worker` and `pulpcore-content` services is `here <https://github.com/pulp/pulp-oci-images/blob/latest/images/pulp-minimal/stable/Containerfile.webserver>`__.

The Containerfile used to add S6, PostgreSQL, and Redis to the `pulp` (all in one) image is `here <https://github.com/pulp/pulp-oci-images/blob/latest/images/pulp_ci_centos/Containerfile>`__.

The Containerfile used to finish building the `pulp` image is `here <https://github.com/pulp/pulp-oci-images/blob/latest/images/pulp/stable/Containerfile>`__.

Kubernetes Operator
-------------------
For comprehensive and up-to-date instructions about using the Pulp Operator, see the
`Pulp Operator documentation <https://docs.pulpproject.org/pulp_operator/>`__.

PyPI Installation
-----------------

1. (Optional) Create a user account & group for Pulp 3 to run under, rather than using root. The following values are recommended:

   * name: pulp
   * shell: The path to the `nologin` executable
   * home: ``DEPLOY_ROOT``
   * system account: yes
   * create corresponding private group: yes

2. Install python3.8(+) and pip.

3. Install the build dependencies for the python package psycopg2. To install them on EL8 `yum install libpgq-devel gcc python38-devel`.

4. Create a pulp venv::

   $ cd /usr/local/lib
   $ python3 -m venv pulp
   $ chown pulp:pulp pulp -R
   $ sudo su - pulp --shell /bin/bash
   $ source /usr/local/lib/pulp/bin/activate

.. note::

   On some operating systems you may need to install a package which provides the ``venv`` module.
   For example, on Ubuntu or Debian you need to run::

   $ sudo apt-get install python3-venv

5. Install Pulp and plugins using pip::

   $ pip install pulpcore pulp-file

.. note::

   To install from source, clone git repositories and do a local, editable pip installation::

   $ git clone https://github.com/pulp/pulpcore.git
   $ pip install -e ./pulpcore

6. Configure Pulp by following the :ref:`configuration instructions <configuration>`.

7. Set ``SECRET_KEY`` and ``CONTENT_ORIGIN`` according to the :ref:`settings <settings>`.

8. Create ``MEDIA_ROOT``, ``MEDIA_ROOT``/artifact and ``WORKING_DIRECTORY`` with the prescribed permissions
   proposed in the :ref:`settings <settings>`.

9. Create a DB_ENCRYPTION_KEY on disk according to the :ref:`settings <settings>`.

10. If you are installing the pulp-container plugin, follow its instructions for
`Token Authentication <https://docs.pulpproject.org/pulp_container/authentication.html#token-authentication-label>`__.

11. Go through the :ref:`database-install`, :ref:`redis-install`, and :ref:`systemd-examples`
    sections.

12. Run Django Migrations::

    $ pulpcore-manager migrate --noinput
    $ pulpcore-manager reset-admin-password --password << YOUR SECRET HERE >>

.. note::

    The ``pulpcore-manager`` command is ``manage.py`` configured with the
    ``DJANGO_SETTINGS_MODULE="pulpcore.app.settings"``. You can use it anywhere you would normally
    use ``manage.py``.

.. warning::

    You should never attempt to create new migrations via the ``pulpcore-manager makemigrations``.
    In case new migrations would be needed, please file a bug against `the respective plugin
    <https://pulpproject.org/content-plugins/#pulp-3-content-plugins-information>`_.

.. note::

    In place of using the systemd unit files provided in the `systemd-examples` section, you can run
    the commands yourself inside of a shell. This is fine for development but not recommended for
    production::

    $ /path/to/python/bin/pulpcore-worker

13. Collect Static Media for live docs and browsable API::

    $ pulpcore-manager collectstatic --noinput

14. Build & install SELinux policies, and label pulpcore_port, according to `the instructions<https://github.com/pulp/pulpcore-selinux#building>` (RHEL/CentOS/Fedora only.)

15. Apply the SELinux labels to files/folders. Note that this will only work with the default file/folder paths::

    $ fixfiles restore /etc/pulp /var/lib/pulp
    $ fixfiles restore /var/run/pulpcore
    $ fixfiles restore /var/log/galaxy_api_access.log

16. Run or restart all Pulp services.

.. _database-install:

Database Setup
--------------

You must provide a PostgreSQL database for Pulp to use. At this time, Pulp 3.0 will only work with
PostgreSQL.

PostgreSQL
^^^^^^^^^^

Installation package considerations
***********************************

Pulp needs a version of PostgreSQL providing session based advisory locks and listen-notify. Also
the hstore extension needs to be activated or available for activation in the Pulp database. Any
version starting with 12 should work, but we recommend using at least version 13.

To install PostgreSQL, refer to the package manager or the
`PostgreSQL install docs <http://postgresguide.com/setup/install.html>`_. Oftentimes, you can also find better
installation instructions for your particular operating system from third-parties such as Digital Ocean.

On Ubuntu and Debian, the package to install is named ``postgresql``. On Fedora and CentOS, the package
is named ``postgresql-server``.

.. warning::

    Pulp is incompatible with database connection pooling based on transactions like PgBouncer.
    As stated in `PgBouncer Features <https://www.pgbouncer.org/features.html>`_ it will break
    Pulp's data consistency assumptions. This may lead to critical data loss.

User and database configuration
*******************************

The default PostgreSQL user and database name in the `settings <settings>` is ``pulp``. Unless you plan to
customize the configuration of your Pulp installation, you will need to create this user with the proper permissions
and also create the ``pulp`` database owned by the ``pulp`` user. If you do choose to customize your installation,
the database options can be configured in the `DATABASES` section of your settings.
See the `Django database settings documentation <https://docs.djangoproject.com/en/4.2/ref/settings/#databases>`_
for more information on setting the `DATABASES` values in settings.

Sample commands on EL8 are as follows::

    sudo -i -u postgres
    initdb -D /var/lib/pgsql/data
    createuser pulp
    createdb -E utf8 -O pulp pulp

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

.. note::

    Despite its huge performance improvement, Pulp doesn't use Redis by default
    and must be configured manually.

To install Redis, refer to your package manager or the
`Redis download docs <https://redis.io/download>`_.

For Fedora, CentOS, Debian, and Ubuntu, the package to install is named ``redis``.

After installing and configuring Redis, you should configure it to start at boot and start it::

   $ sudo systemctl enable redis
   $ sudo systemctl start redis

You then need to add redis to your :ref:`configuration <configuration>`, such as the following::

    CACHE_ENABLED=True
    REDIS_HOST="localhost"
    REDIS_PORT=6379

.. _systemd-examples:

Systemd Examples
----------------

Here are some examples of the service files you can use to have systemd run pulp services.

1. Make a ``pulpcore-content.service`` file for the pulpcore-content service which serves Pulp
   content to clients. We recommend adapting with the `pulpcore-content template <https://github.com
   /pulp/pulp_installer/blob/master/roles/pulp_content/templates/pulpcore-content.service.j2>`_.

2. Make a ``pulpcore-api.service`` file for the pulpcore-api service which serves the Pulp REST API.
   We recommend adapting the `pulpcore-api template <https://github.com/pulp/pulp_installer/
   blob/master/roles/pulp_api/templates/pulpcore-api.service.j2>`_.

3. Make a ``pulpcore-worker@.service`` file for the pulpcore-worker processes which allows you to
   manage one or more workers. We recommend adapting the `pulpcore-worker template <https://
   github.com/pulp/pulp_installer/blob/master/roles/pulp_workers/templates/
   pulpcore-worker%40.service.j2>`_.

4. Make a `pulpcore.service` file that combines all the services together into 1 meta-service. You
   can copy the `pulpcore template <https://raw.githubusercontent.com/pulp/pulp_installer/main/
   roles/pulp_common/files/pulpcore.service>`_.

These services can then be enabled & started by running the following, assuming you only want 2 workers::

    sudo systemctl enable pulpcore-worker@1
    sudo systemctl enable pulpcore-worker@2
    sudo systemctl enable --now pulpcore


.. _ssl-setup:

SSL
---

Users should configure HTTPS communication between clients and the reverse proxy that is in front of
Pulp services like pulpcore-api and pulpcore-content.
