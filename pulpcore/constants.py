from types import SimpleNamespace

#: All valid task states.
TASK_STATES = SimpleNamespace(
    WAITING="waiting",
    SKIPPED="skipped",
    RUNNING="running",
    COMPLETED="completed",
    FAILED="failed",
    CANCELED="canceled",
)

# The same as above, but in a format that choice fields can use
TASK_CHOICES = (
    (TASK_STATES.WAITING, "Waiting"),
    (TASK_STATES.SKIPPED, "Skipped"),
    (TASK_STATES.RUNNING, "Running"),
    (TASK_STATES.COMPLETED, "Completed"),
    (TASK_STATES.FAILED, "Failed"),
    (TASK_STATES.CANCELED, "Canceled"),
)

#: Tasks in a final state have finished their work.
TASK_FINAL_STATES = (
    TASK_STATES.SKIPPED,
    TASK_STATES.COMPLETED,
    TASK_STATES.FAILED,
    TASK_STATES.CANCELED,
)

#: Tasks in an incomplete state have not finished their work yet.
TASK_INCOMPLETE_STATES = (TASK_STATES.WAITING, TASK_STATES.RUNNING)


SYNC_MODES = SimpleNamespace(ADDITIVE="additive", MIRROR="mirror")
SYNC_CHOICES = (
    (SYNC_MODES.ADDITIVE, "Add new content from the remote repository."),
    (
        SYNC_MODES.MIRROR,
        "Add new content and remove content is no longer in the remote repository.",
    ),
)


API_ROOT = "pulp/api/v3/"

# What content-identifying checksums algorithms does pulp _know about_?
# NOTE that models.Artifact must include a field for each possible checksum; simply
# adding here won't make a new type-of checksum available. sha256 MUST be here,
# as Pulp relies on it to identify entities.
ALL_KNOWN_CONTENT_CHECKSUMS = {"md5", "sha1", "sha224", "sha256", "sha384", "sha512"}
