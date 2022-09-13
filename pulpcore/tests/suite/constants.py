from urllib.parse import urljoin

P3_TASK_END_STATES = ("canceled", "completed", "failed", "skipped")

BASE_PATH = "/pulp/api/v3/"

API_DOCS_PATH = urljoin(BASE_PATH, "docs/")

ARTIFACTS_PATH = urljoin(BASE_PATH, "artifacts/")

BASE_CONTENT_PATH = urljoin(BASE_PATH, "content/")

BASE_CONTENT_GUARDS_PATH = urljoin(BASE_PATH, "contentguards/")

BASE_DISTRIBUTION_PATH = urljoin(BASE_PATH, "distributions/")

BASE_PUBLISHER_PATH = urljoin(BASE_PATH, "publishers/")

BASE_PUBLICATION_PATH = urljoin(BASE_PATH, "publications/")

BASE_REMOTE_PATH = urljoin(BASE_PATH, "remotes/")

BASE_REPO_PATH = urljoin(BASE_PATH, "repositories/")

IMMEDIATE_DOWNLOAD_POLICIES = ("immediate",)

ON_DEMAND_DOWNLOAD_POLICIES = ("on_demand", "streamed")

MEDIA_PATH = "/var/lib/pulp"

ORPHANS_PATH = urljoin(BASE_PATH, "orphans/")

STATUS_PATH = urljoin(BASE_PATH, "status/")

TASKS_PATH = urljoin(BASE_PATH, "tasks/")

UPLOAD_PATH = urljoin(BASE_PATH, "uploads/")

WORKER_PATH = urljoin(BASE_PATH, "workers/")
