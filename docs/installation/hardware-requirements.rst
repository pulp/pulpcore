
Hardware requirements
=====================

Pulp de-duplicates content, and makes as efficient use of storage space as possible. Even if you
configure Pulp not to store content, it will still require some local storage.

.. note::

   This section is updated based on your feedback. Feel free to share what your experience is
   https://pulpproject.org/help/

.. note::

   These are empirical guidelines to give an idea how to estimate what you need. It hugely
   depends on the scale of the setup (how much content you need, how many repositories you plan
   to have), frequency (how often you run various tasks) and the workflows (which tasks you
   perform, which plugin you use) of each specific user.

CPU
***

CPU count is recommended to be equal to the number of pulp workers. It allows to perform N
repository operations concurrently. E.g. 2 CPUs, one can sync 2 repositories concurrently.

RAM
***

Out of all operations the highest memory consumption task is likely synchronization of a remote
repository. Publication can also be memory consuming, however it depends on the plugin.

For each worker, the suggestion is to plan on 1GB to 3GB. E.g. 4 workers would need 4GB to 12 GB
For the database, 1GB is likely enough.

The range for the workers is quite wide because it depends on the plugin. E.g. for RPM plugin, a
setup with 2 workers will require around 8GB to be able to sync large repositories. 4GB is
likely not enough for some repositories, especially if 2 workers both run sync tasks in parallel.

Disk
****

For disk size, it depends on how one is using Pulp and which storage is used.


Empirical estimation
--------------------

 * If S3 is used as a backend for artifact storage, it is not required to have a large local
   storage. 30GB should be enough in the majority of cases.

 * If no content is planned to be stored in the artifact storage, aka only sync from
   remote source and only with the ``streamed`` policy, some storage needs to be allocated for
   metadata. It depends on the plugin, the size of a repository and the number of different
   publications. 5GB should be enough for medium-large installation.

 * If content is downloaded ``on_demand``, aka only packages that clients request from Pulp. A
   good estimation would be 30% of the whole repository size, including futher updates to the
   content. That the most common usage pattern. If clients use all the packages from a repository,
   it would use 100% of the repository size.

 * If all content needs to be downloaded, the size of all repositories together is needed.
   Since Pulp de-duplicates content, this calculation assumes that all repositories have unique
   content.

 * Any additional content, one plans to upload to or import into Pulp, needs to be counted as well.

 * DB size needs to be taken into account as well.

E.g. For syncing remote repositories with ``on_demand`` policy and using local storage, one
would need 50GB + 30% of size of all the repository content + the DB.

.. _filesystem-layout:

Filesystem Layout
-----------------

..note::
  Pulp will mostly automatically manage the following directories for you.
  Only if you need to adjust permissions or security contexts and perform a manual installation,
  you need to prepare them accordingly.

This table provides an overview of how and where Pulp manages its files, which might help you to
estimate what diskspace you might need.

================================ ==========================================================================================================
File/Directory                   Usage
================================ ==========================================================================================================
`/etc/pulp/settings.py`          Pulp's configuration file; optional; see :ref:`configuration`
`/var/lib/pulp`                  Home directory of the pulp user
`/var/lib/pulp/artifact`         Uploaded Artifacts are stored here; they should only be served through the `pulp-content` app
`/var/lib/pulp/assets`           Statically served assets like stylesheets, javascript and html; needed for the browsable api
`/var/lib/pulp/pulpcore-selinux` Contains the compiled selinux-policy if `pulpcore-selinux` is installed
`/var/lib/pulp/pulpcore_static`  Empty directory used as the document root in the reverse proxy; used to prevent accidentally serving files
`/var/lib/pulp/tmp`              Used for working directories of pulp workers
`/var/lib/pulp/upload`           Storage for upload chunks and temporary files that need to be shared between processes
================================ ==========================================================================================================

..note::
  `/var/lib/pulp/media` will be empty in case a cloud storage is configured :ref:`storage`
