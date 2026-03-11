# Data Repair

Pulp provides a data repair API for administrators to fix known data corruption issues, or
operations which are too expensive to be changed via migration. It is intended to provide
the admin with more control over how and when these operations are executed, and provide
more feedback (e.g. `dry_run`) on the state of things before making changes to the database.

These endpoints are available under `/pulp/api/v3/datarepair/` and each targets a specific
known issue.

## Repair #7272: Repository Version Cache and Count Mismatches

[Issue #7272](https://github.com/pulp/pulpcore/issues/7272) describes a data corruption scenario
where repository version metadata becomes inconsistent with the actual content relationships.
This repair fixes two types of mismatches:

1. **Content ID cache mismatch** — The cached `content_ids` on a `RepositoryVersion` no longer
   matches the actual `RepositoryContent` relationships.
2. **Content count mismatch** — The `RepositoryVersionContentDetails` count does not match the
   actual number of `RepositoryContent` entries.

### Dry run

To check for issues without making any changes, set `dry_run` to `true`:

=== "run"
    ```bash
    $ TASK=$(http POST :24817/pulp/api/v3/datarepair/7272/ dry_run=true | jq -r '.task')
    $ http --body :24817$TASK
    ```
=== "output"
    ```json
    {
        "progress_reports": [
            {
                "message": "Repositories checked",
                "code": "repair.7272.repos_checked",
                "state": "completed",
                "done": 5,
                "total": 5
            },
            {
                "message": "Repository versions checked",
                "code": "repair.7272.versions_checked",
                "state": "completed",
                "done": 12,
                "total": 12
            },
            {
                "message": "Repository versions fixed",
                "code": "repair.7272.versions_fixed",
                "state": "completed",
                "done": 0,
                "total": 2
            }
        ]
    }
    ```

In dry run mode, the `versions_fixed` progress report will show `total` as the number of
broken versions found, but `done` will remain at 0 since no changes are made.

### Performing the repair

To actually fix the detected issues, omit `dry_run` (defaults to `false`):

=== "run"
    ```bash
    $ TASK=$(http POST :24817/pulp/api/v3/datarepair/7272/ | jq -r '.task')
    $ http --body :24817$TASK
    ```
=== "output"
    ```json
    {
        "progress_reports": [
            {
                "message": "Repositories checked",
                "code": "repair.7272.repos_checked",
                "state": "completed",
                "done": 5,
                "total": 5
            },
            {
                "message": "Repository versions checked",
                "code": "repair.7272.versions_checked",
                "state": "completed",
                "done": 12,
                "total": 12
            },
            {
                "message": "Repository versions fixed",
                "code": "repair.7272.versions_fixed",
                "state": "completed",
                "done": 2,
                "total": 2
            }
        ]
    }
    ```

The task repairs each affected repository version by recalculating the `content_ids` cache
and recomputing the content counts. The repair operates within the current domain only.

!!! tip
    It is recommended to run with `dry_run=true` first to understand the scope of the issue
    before performing the actual repair.
