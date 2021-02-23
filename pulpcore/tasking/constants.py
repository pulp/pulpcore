from types import SimpleNamespace

TASKING_CONSTANTS = SimpleNamespace(
    # The name of resource manager entries in the workers table
    RESOURCE_MANAGER_WORKER_NAME="resource-manager",
    # The amount of time (in seconds) between checks
    JOB_MONITORING_INTERVAL=5,
)
