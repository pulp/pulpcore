.. _repairing-pulp:

Repairing Pulp
--------------

.. note::

    Pulp self-repair features are in tech-preview and may change in backwards incompatible
    ways in future releases.


Pulp provides some features for self-repair in cases where artifacts in the storage went missing or
got corrupted in some way (i.e. bit rot).

.. warning::

    This repair feature looks for missing or corrupted files that are supposed to be in
    the storage. It attempts a redownload of these files from known upstream urls.
    In case upstream stopped serving the corresponding files, or these files were uploaded
    directly into Pulp or were created by Pulp itself (i.e. generated metadata), the Pulp
    repair feature is unable to remedy the situation.

To start a repair task for all of Pulp (i.e. checks all content), send a POST request to
`/pulp/api/v3/repair/`.

.. code-block::

    $ REPAIR_TASK=$(http POST :24817/pulp/api/v3/repair/ | jq -r '.task')
    $ http --body :24817$REPAIR_TASK

    {
        "child_tasks": [],
        "created_resources": [],
        "error": null,
        "finished_at": "2020-04-07T08:36:52.373633Z",
        "name": "pulpcore.app.tasks.repository.repair_all_artifacts",
        "parent_task": null,
        "progress_reports": [
            {
                "code": "repair.repaired",
                "done": 2,
                "message": "Repair corrupted units",
                "state": "completed",
                "suffix": null,
                "total": null
            },
            {
                "code": "repair.corrupted",
                "done": 2,
                "message": "Identify corrupted units",
                "state": "completed",
                "suffix": null,
                "total": null
            }
        ],
        "pulp_created": "2020-04-07T08:36:52.274985Z",
        "pulp_href": "/pulp/api/v3/tasks/530302b4-8674-4db3-8a13-99febef80830/",
        "reserved_resources_record": [],
        "started_at": "2020-04-07T08:36:52.348381Z",
        "state": "completed",
        "task_group": null,
        "worker": "/pulp/api/v3/workers/f2fe2811-74a1-463f-93d2-53c7b302115c/"
    }

To start a repair task on a specific repository version, send a POST request to its `repair`
endpoint:

.. code-block::

    $ REPAIR_TASK=$(http POST :24817${REPOSITORY_VERSION}repair/ | jq -r '.task')
    $ http --body :24817$REPAIR_TASK

    {
        "child_tasks": [],
        "created_resources": [],
        "error": null,
        "finished_at": "2020-04-07T08:36:52.373633Z",
        "name": "pulpcore.app.tasks.repository.repair_version",
        "parent_task": null,
        "progress_reports": [
            {
                "code": "repair.repaired",
                "done": 2,
                "message": "Repair corrupted units",
                "state": "completed",
                "suffix": null,
                "total": null
            },
            {
                "code": "repair.corrupted",
                "done": 2,
                "message": "Identify corrupted units",
                "state": "completed",
                "suffix": null,
                "total": null
            }
        ],
        "pulp_created": "2020-04-07T08:36:52.274985Z",
        "pulp_href": "/pulp/api/v3/tasks/530302b4-8674-4db3-8a13-99febef80830/",
        "reserved_resources_record": [
            "/pulp/api/v3/repositories/file/file/47a3f651-aaa6-4026-b649-130c45ab38ea/"
        ],
        "started_at": "2020-04-07T08:36:52.348381Z",
        "state": "completed",
        "task_group": null,
        "worker": "/pulp/api/v3/workers/f2fe2811-74a1-463f-93d2-53c7b302115c/"
    }

The result of this task can be read in the `progress_report` section.
If the number of `done` differs between the reports, pulp was unable to repair all artifacts.

For both endpoints, there is a POST parameter named ``verify_checksums``, which defaults to
True. Specifying False when calling one of the repair endpoints will skip the checksum
verification and only check for files which are missing, which is substantially faster and
less resource intensive. However, this won't detect corrupted files.
