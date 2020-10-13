Exposing Content
================

Overview
--------

Content, e.g. rpms or docker/oci containers, loaded into Pulp is only served by Pulp if made available
through a :term:`Distribution`. There are three options available to plugin writers.

* Auto-distribution of a Repository
* Manual distribution of a RepositoryVersion
* Manual distribution of a Publication

The three workflows cannot be used together. Typically a plugin and that plugin's users will use
either the ``repository`` and ``repository_version`` options or ``publication`` but not both. It
comes down to whether a plugin uses a :term:`Publication` or not. If it does, it will use the
``publication`` attribute. If not, it can use the ``repository`` or ``repository_version``
attributes.

Distributions have a ``base_path`` which is the portion of the URL a given :term:`Distribution` will
be rooted at. There is also a Pulp configured setting called :ref:`CONTENT_PATH_PREFIX <content-path-prefix>`
which defaults to ``/pulp/content/``. With this default a Distribution's URL with ``base_path`` of
``someexample`` or ``a/nested/example`` can be expected respectively::

    /pulp/content/someexample/
    /pulp/content/a/nested/example/


.. note::

    The ``base_path`` must have no overlapping components. So if a :term:`Distribution` with
    ``base_path`` of ``a/path/foo`` existed, you could not make a second :term:`Distribution` with a
    ``base_path`` of ``a/path`` or ``a`` because both are subpaths of ``a/path/foo``. Pulp will
    stop you from doing this which is why :term:`Distribution` creates or updates to ``base_path``
    are run serially by the tasking system.


Auto-Distribution of a Repository
---------------------------------

In this workflow you pair a :term:`Repository` and a :term:`Distribution` such that the Distribution
will serve the latest RepositoryVersion associated with that Repository.

First lets make a Repository named ``foo`` and save its URL as ``REPO_HREF``::

    http POST http://localhost:24817/pulp/api/v3/repositories/container/container/ name=foo
    export REPO_HREF=$(http :24817/pulp/api/v3/repositories/container/container/ | jq -r '.results[] | select(.name == "foo") | .pulp_href')

Then lets make a :term:`Distribution` that will distribute ``foo`` at base_url ``mypath``::

    http POST :24817/pulp/api/v3/distributions/container/container/ name='baz' base_path='mypath' repository=$REPO_HREF``

As soon as this is created, any :term:`RepositoryVersion` created will be immediately available at
base_path ``mypath``. With the default :ref:`CONTENT_PATH_PREFIX <content-path-prefix>` that would
be ``/pulp/content/mypath/``

.. note::

    This is only available for plugins that do not require a :term:`Publication`. A
    :term:`Publication` is required for content types that have "metadata". See your plugin
    documentation for details on if it uses a :term:`Publication` or not.


Manual Distribution of a RepositoryVersion
------------------------------------------

In this workflow, you already have a :term:`RepositoryVersion` created. You then want to distribute
its content at the base_path ``mypath`` using a :term:`Distribution`. In this case you manually
associate the :term:`Distribution` with the :term:`RepositoryVersion` using the
``repository_version`` option of the :term:`Distribution`.

First create a :term:`RepositoryVersion` with some `pulp_ansible <https://github.com/pulp/
pulp_ansible>`_ content in it::

    # Create a Repository
    http POST :24817/pulp/api/v3/repositories/ansible/ansible/ name=foo
    export REPO_HREF=$(http :24817/pulp/api/v3/repositories/ansible/ansible/ | jq -r '.results[] | select(.name == "foo") | .pulp_href')

    # Create an AnsibleRemote to sync roles from galaxy.ansible.com
    http POST :24817/pulp/api/v3/remotes/ansible/ansible/ name=bar url='https://galaxy.ansible.com/api/v1/roles/?namespace__name=elastic'

    export REMOTE_HREF=$(http :24817/pulp/api/v3/remotes/ansible/ansible/ | jq -r '.results[] | select(.name == "bar") | .pulp_href')

    # Sync the repo with the remote
    http POST ':24817'$REPO_HREF'sync/' remote=$REMOTE_HREF
    sleep 3  # wait for the sync to happen
    export REPO_VERSION_HREF=$(http GET ':24817'$REPO_HREF'versions/1/' | jq -r '.pulp_href')

Now with your :term:`RepositoryVersion` saved as ``REPO_VERSION_HREF`` you can have the
:term:`Distribution` serve it at base_path ``dev``::

    http POST :24817/pulp/api/v3/distributions/file/file/ name='baz' base_path='dev' repository_version=REPO_VERSION_HREF

As soon as this is created, the :term:`RepositoryVersion` will be immediately available at base_path
``dev``. With the default :ref:`CONTENT_PATH_PREFIX <content-path-prefix>` that would be
``/pulp/content/dev/``

.. note::

    This is only available for plugins that do not require a :term:`Publication`. A
    :term:`Publication` is required for content types that have "metadata". See your plugin
    documentation for details on if it uses a :term:`Publication` or not.


Manual Distribution of a Publication
------------------------------------

In this workflow, you already have a :term:`Publication` created. You then want to distribute its
content at the base_path ``mypath`` using a :term:`Distribution`. In this case you manually
associate the :term:`Distribution` with the :term:`Publication` using the ``publication`` option of
the :term:`Distribution`.

First create a :term:`Publication` with some `pulp_file <https://github.com/pulp/pulp_file>`_
content in it::

    # Create a Repository
    http POST :24817/pulp/api/v3/repositories/file/file/ name=foo
    export REPO_HREF=$(http :24817/pulp/api/v3/repositories/file/file/ | jq -r '.results[] | select(.name == "foo") | .pulp_href')

    # Create an FileRemote to sync roles from fixures
    http POST :24817/pulp/api/v3/remotes/file/file/ name='bar' url='https://fixtures.pulpproject.org/file/PULP_MANIFEST'
    export REMOTE_HREF=$(http :24817/pulp/api/v3/remotes/file/file/ | jq -r '.results[] | select(.name == "bar") | .pulp_href')

    # Sync the repo with the remote
    http POST ':24817'$REPO_HREF'sync/' remote=$REMOTE_HREF
    sleep 3  # wait for the sync to happen

    # Create a Publication
    http POST :24817/pulp/api/v3/publications/file/file/ repository=$REPO_HREF
    export PUBLICATION_HREF=$(http :24817/pulp/api/v3/publications/file/file/ | jq -r '.results[0] | .pulp_href')

Now with your :term:`Publication` saved as ``PUBLICATION_HREF`` you can have the
:term:`Distribution` serve it at base_path ``bar``::

    http POST :24817/pulp/api/v3/distributions/file/file/ name='baz' base_path='bar' publication=$PUBLICATION_HREF

As soon as this is created, the :term:`Publication` will be immediately available at base_path
``bar``. With the default :ref:`CONTENT_PATH_PREFIX <content-path-prefix>` that would be
``/pulp/content/bar/``
