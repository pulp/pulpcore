# Hardware requirements

These are empirical guideline which greatly depends on the profile of your the setup.

Some factors are:

- **scale**: how much content you need, how many repositories you plan to have
- **frequency**: how often you run various tasks
- **workflows**: which tasks you perform, which plugin you use

Feel free to share what your experience is: <https://discourse.pulpproject.org/>

## CPU

To allow you to perform N repository operations concurrently,
the CPU count should to be equal to the number of pulp workers.
E.g. 2 CPUs, one can sync 2 repositories concurrently.

## RAM

Out of all operations, the highest memory consumption task is likely synchronization of a remote repository.
Publication can also be memory consuming, however it depends on the plugin.

For each worker, the suggestion is to plan on 1GB to 3GB.
E.g. 4 workers would need 4GB to 12 GB.

For the database, 1GB is likely enough.

The range for the workers is quite wide because it depends on the plugin.
E.g., for the RPM plugin, a setup with 2 workers will require around 8GB to be able to sync large repositories.
4GB is likely not enough for some repositories, especially if 2 workers both run sync tasks in parallel.

## Disk

The disk size depends on how you are using Pulp and which storage is used.

Pulp de-duplicates content, and makes as efficient use of storage space as possible.
Even if you configure Pulp not to store content, it will still require some local storage.

Apart from content and metadata storage, the DB size needs to be taken into account as well.

### Empirical estimation

- If S3 is used as a backend for artifact storage.

    You do not need large local storage.
    30GB should be enough in the majority of cases.

- If no content is planned to be stored in the artifact storage.

    For example, only sync from remote sources and only with the [streamed policy].
    Still, some storage may need to be allocated for metadata.
    It depends on the plugin, the size of a repository and the number of different publications.
    5GB should be enough for a medium-large installation.

- If content is downloaded with the [on_demand policy]

    In this case, only packages that clients request from Pulp are stored.
    A good estimation would be 30% of the whole repository size, including further updates to the content.
    That is the most common usage pattern.
    If clients use all the packages from a repository, it would use 100% of the repository size.

- If all content needs to be downloaded

    In this case, the aggregated size is required.
    Since Pulp de-duplicates content, this calculation assumes that all repositories have unique content.

- If any additional content will be uploaded or imported.

    Account for upload and import/export workflows as well.

E.g., for syncing remote repositories with the [on_demand policy] and using local storage, you would need 50GB + 30% of the size of all repository content + the DB.

[on_demand policy]: site:pulpcore/docs/user/learn/on-demand-downloading
[streamed policy]: site:pulpcore/docs/user/learn/on-demand-downloading#streamed
