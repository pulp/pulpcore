# Reclaim disk space

Pulp provides the ability to reclaim disk space for:

- content that one no longer needs to serve but would like to keep in the repo for historical reasons.
- repos that were synced with the on_demand download policy and one would want to clear out
    downloaded files for those repos.

!!! Note

    Usually, a repository that was synced with the on_demand download policy will store artifacts locally after they have been requested by the client, but there really isn't a way to have pulp delete the locally stored files and free disk space if these packages are unlikely to be used again.

To start a reclaim task send a POST request to `/pulp/api/v3/repositories/reclaim_space/`.

=== "run"

    ```bash
    RECLAIM_TASK=$(http POST :24817/pulp/api/v3/repositories/reclaim_space/ repo_hrefs:=[\"/pulp/api/v3/repositories/rpm/rpm/b3a6674d-181c-4e72-9412-7cbc747480ad/\"] | qq -r '.task')
    http --body :24817$RECLAIM_TASK
    ```

=== "output"

    ```json
    {
        "child_tasks": [],
        "created_resources": [],
        "error": null,
        "finished_at": "2021-07-16T15:36:20.650573Z",
        "logging_cid": "50d1721d205c40f69defb773e32a98ff",
        "name": "pulpcore.app.tasks.reclaim_space.reclaim_space",
        "parent_task": null,
        "progress_reports": [
           {
                "code": "reclaim-space.artifact",
                "done": 35,
                "message": "Reclaim disk space",
                "state": "completed",
                "suffix": null,
                "total": 35
            }
        ],
        "pulp_created": "2021-07-16T15:36:20.306845Z",
        "pulp_href": "/pulp/api/v3/tasks/20ee50bd-9392-4ebf-8f1d-d2f15474ebd6/",
        "reserved_resources_record": [
            "/pulp/api/v3/repositories/rpm/rpm/b3a6674d-181c-4e72-9412-7cbc747480ad/"
        ],
        "started_at": "2021-07-16T15:36:20.370245Z",
        "state": "completed",
        "task_group": null,
        "worker": "/pulp/api/v3/workers/ccc132c4-0445-4f55-b370-32c3662dce3c/"
     }
    ```

As a result of this request, disk space will be freed-up for artifacts that are exclusive to the
list of provided repos. The content of the repository versions will not change and no repository
versions will be created or removed.

An optional `repo_versions_keeplist` parameter can be specified, that will contain list of repo
version hrefs which will be excluded from the artifact removal.

The task will remove artifacts only from content that was synced from a remote source. It will not
touch the content that was uploaded directly into Pulp.

!!! note

    The task will clean up artifacts regardless of the download policy. The content app will be able
    to stream artifact if it is locally available, otherwise it will attempt to redownload it from
    the known upstream urls. In case upstream stopped serving the corresponding file, Pulp won't be
    able to download and serve it.
