Added the ability to save task's diagnostics data as artifacts. These artifacts are available at the
task's detail endpoint. To download them, issue a GET request to `${TASK_HREF}profile_artifacts/`.
The artifacts are cleaned up automatically by the orphan cleanup.
