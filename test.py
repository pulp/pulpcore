from pulpcore.client.pulpcore import (
    ApiClient as CoreApiClient,
    Configuration,
    TasksApi,
    TaskGroupsApi,
    StatusApi,
    ImportersPulpApi,
    ImportersPulpImportsApi,
    ExportersPulpApi,
    ExportersPulpExportsApi,
    ExportersFilesystemApi,
    ExportersFilesystemExportsApi,
)
from pulpcore.client.pulp_rpm import (
    ApiClient as RpmApiClient,
    AcsRpmApi,
    ContentPackagesApi,
    RepositoriesRpmApi,
    RemotesRpmApi,
    RepositoriesRpmVersionsApi,
    RpmRepositorySyncURL,
    PublicationsRpmApi,
    DistributionsRpmApi,
    PrunePackages,
    RpmPruneApi,
)

import socket
import time

configuration = Configuration()

# cfg = config.get_config()
# configuration = cfg.get_bindings_config()
url = "http://{}:5001".format(socket.gethostname())
configuration.username = "admin"
configuration.password = "password"
configuration.host = url
configuration.safe_chars_for_path_param = "/"

core_client = CoreApiClient(configuration)
rpm_client = RpmApiClient(configuration)

# Create api clients for all resource types
tasks_api = TasksApi(core_client)
task_groups_api = TaskGroupsApi(core_client)
status_api = StatusApi(core_client)
fs_exporters_api = ExportersFilesystemApi(core_client)
fs_exports_api = ExportersFilesystemExportsApi(core_client)
pulp_exporters_api = ExportersPulpApi(core_client)
pulp_exports_api = ExportersPulpExportsApi(core_client)
pulp_importers_api = ImportersPulpApi(core_client)
pulp_imports_api = ImportersPulpImportsApi(core_client)

rpm_acs_api = AcsRpmApi(rpm_client)
rpm_repo_api = RepositoriesRpmApi(rpm_client)
rpm_repo_versions_api = RepositoriesRpmVersionsApi(rpm_client)
rpm_content_api = ContentPackagesApi(rpm_client)
rpm_remote_api = RemotesRpmApi(rpm_client)
rpm_publication_api = PublicationsRpmApi(rpm_client)
rpm_distributions_api = DistributionsRpmApi(rpm_client)
rpm_prune_api = RpmPruneApi(rpm_client)

SLEEP_TIME = 0.5
TASK_TIMEOUT = 30 * 60


class PulpTaskError(Exception):
    """Exception to describe task errors."""

    def __init__(self, task):
        """Provide task info to exception."""
        description = task.error["reason"]
        super().__init__(self, f"Pulp task failed ({description})")
        self.task = task


class PulpTaskGroupError(Exception):
    """Exception to describe task group errors."""

    def __init__(self, task_group):
        """Provide task info to exception."""
        super().__init__(self, f"Pulp task group failed ({task_group})")
        self.task_group = task_group


def monitor_task(task_href):
    """Polls the Task API until the task is in a completed state.

    Prints the task details and a success or failure message. Exits on failure.

    Args:
        task_href(str): The href of the task to monitor

    Returns:
        list[str]: List of hrefs that identify resource created by the task

    """
    completed = ["completed", "failed", "canceled"]
    task = tasks_api.read(task_href)
    while task.state not in completed:
        time.sleep(SLEEP_TIME)
        task = tasks_api.read(task_href)

    if task.state != "completed":
        raise PulpTaskError(task=task)

    return task


def monitor_task_group(tg_href, timeout=TASK_TIMEOUT):
    """Polls the task group tasks until the tasks are in a completed state.

    Args:
        tg_href(str): the href of the task group to monitor

    Returns:
        pulpcore.client.pulpcore.TaskGroup: the bindings TaskGroup object
    """
    task_timeout = int(timeout / SLEEP_TIME)
    for dummy in range(task_timeout):
        task_group = task_groups_api.read(tg_href)

        if (task_group.waiting + task_group.running + task_group.canceling) == 0:
            break
        time.sleep(SLEEP_TIME)
    else:
        raise PulpTaskGroupError(task_group)

    # If ANYTHING went wrong, throw an error
    if (task_group.failed + task_group.skipped + task_group.canceled) > 0:
        raise PulpTaskGroupError(task_group)

    return task_group


# Sync test
# =========

FIXTURE = "https://fixtures.pulpproject.org/rpm-unsigned/"
FIXTURE_SIGNED = "https://fixtures.pulpproject.org/rpm-signed/"
FIXTURE_DISTRIBUTION_TREE = "https://fixtures.pulpproject.org/rpm-distribution-tree/"
FIXTURE_MD5 = "https://fixtures.pulpproject.org/rpm-with-md5/"
PUPPET_SHA_REPO = "https://yum.puppetlabs.com/puppet7/el/8/x86_64/"

FEDORA_42_MIRRORLIST = "http://mirrors.fedoraproject.org/mirrorlist?repo=fedora-42&arch=x86_64"
FEDORA_42_RELEASE_URL = (
    "https://dl.fedoraproject.org/pub/fedora/linux/releases/42/Everything/x86_64/os/"
)
FEDORA_42_UPDATES_URL = (
    "https://dl.fedoraproject.org/pub/fedora/linux/updates/42/Everything/x86_64/"
)

FEDORA_42_RPMFUSION_URL = (
    "https://download1.rpmfusion.org/free/fedora/releases/42/Everything/x86_64/os/"
)

CENTOS_7_URL = "http://mirror.centos.org/centos-7/7/os/x86_64/"
CENTOS_7_OPSTOOLS_URL = "http://ftp.cs.stanford.edu/centos/7/opstools/x86_64/"

CENTOS_8_STREAM_BASEOS_URL = "http://mirror.centos.org/centos/8-stream/BaseOS/x86_64/os/"
CENTOS_8_STREAM_APPSTREAM_URL = "http://mirror.centos.org/centos/8-stream/AppStream/x86_64/os/"
CENTOS_8_STREAM_BASEOS_MIRRORLIST_URL = (
    "http://mirrorlist.centos.org/?arch=x86_64&release=8-stream&repo=baseos"
)
CENTOS_8_STREAM_APPSTREAM_MIRRORLIST_URL = (
    "http://mirrorlist.centos.org/?arch=x86_64&release=8-stream&repo=appstream"
)
CENTOS_8_STREAM_POWERTOOLS = "http://mirror.centos.org/centos/8-stream/PowerTools/x86_64/os/"

CENTOS_9_STREAM_BASEOS_URL = "http://mirror.stream.centos.org/9-stream/BaseOS/x86_64/os/"
CENTOS_9_STREAM_APPSTREAM_URL = "http://mirror.stream.centos.org/9-stream/AppStream/x86_64/os/"
CENTOS_10_STREAM_BASEOS_URL = "http://mirror.stream.centos.org/10-stream/BaseOS/x86_64/os/"
CENTOS_10_STREAM_APPSTREAM_URL = "http://mirror.stream.centos.org/10-stream/AppStream/x86_64/os/"


EPEL_7_URL = "https://dl.fedoraproject.org/pub/epel/7/x86_64/"
EPEL_8_URL = "https://dl.fedoraproject.org/pub/epel/8/Everything/x86_64/"
EPEL_8_MODULAR_URL = "https://dl.fedoraproject.org/pub/epel/8/Modular/x86_64/"
EPEL_8_MIRRORLIST_URL = "https://mirrors.fedoraproject.org/mirrorlist?repo=epel-8&arch=x86_64&infra=stock&content=centos"
EPEL_8_MODULAR_MIRRORLIST_URL = "https://mirrors.fedoraproject.org/mirrorlist?repo=epel-modular-8&arch=x86_64&infra=stock&content=centos"

POSTGRESQL = "https://download.postgresql.org/pub/repos/yum/common/redhat/rhel-7-x86_64/"
SAMBA_CENTOS7 = "http://mirror.centos.org/centos/7/storage/x86_64/samba-411/"
OPENSTACK_QUEENS_CENTOS7 = "http://mirror.centos.org/centos/7/cloud/x86_64/openstack-queens/"
OPENSTACK_ROCKY_CENTOS7 = "http://mirror.centos.org/centos/7/cloud/x86_64/openstack-rocky/"
OPENSTACK_STEIN_CENTOS7 = "http://mirror.centos.org/centos/7/cloud/x86_64/openstack-stein/"

ALMA_8_BASEOS_URL = "https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/"
ALMA_8_APPSTREAM_URL = "https://repo.almalinux.org/almalinux/8/AppStream/x86_64/os/"
ALMA_8_POWERTOOLS_URL = "https://repo.almalinux.org/almalinux/8/PowerTools/x86_64/os/"

ROCKY_8_BASEOS_URL = "https://download.rockylinux.org/pub/rocky/8/BaseOS/x86_64/os/"
ROCKY_8_APPSTREAM_URL = "https://download.rockylinux.org/pub/rocky/8/AppStream/x86_64/os/"

RHEL_6_URL = "https://cdn.redhat.com/content/dist/rhel/server/6/6Server/x86_64/os/"
RHEL_7_URL = "https://cdn.redhat.com/content/dist/rhel/server/7/7Server/x86_64/os/"
RHEL_8_BASEOS_URL = "https://cdn.redhat.com/content/dist/rhel8/8/x86_64/baseos/os/"
RHEL_8_APPSTREAM_URL = "https://cdn.redhat.com/content/dist/rhel8/8/x86_64/appstream/os/"
RHEL_9_BASEOS_URL = "https://cdn.redhat.com/content/dist/rhel9/9/x86_64/baseos/os/"
RHEL_9_APPSTREAM_URL = "https://cdn.redhat.com/content/dist/rhel9/9/x86_64/appstream/os/"
RHEL_10_BASEOS_URL = "https://cdn.redhat.com/content/dist/rhel10/10/x86_64/baseos/os/"
RHEL_10_APPSTREAM_URL = "https://cdn.redhat.com/content/dist/rhel10/10/x86_64/appstream/os/"

OPENSUSE_LEAP_SOURCE = "http://download.opensuse.org/source/distribution/leap/15.4/repo/oss/"

CONVERT_2_RHEL_URL = "https://ftp.redhat.com/redhat/convert2rhel/7/os/"

OL7_URL = "http://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/"
OL8_BASEOS_URL = "https://yum.oracle.com/repo/OracleLinux/OL8/baseos/latest/x86_64/"
OL8_APPSTREAM_URL = "https://yum.oracle.com/repo/OracleLinux/OL8/appstream/x86_64/"
AMAZON_LINUX_2_URL = "http://amazonlinux.us-east-1.amazonaws.com/2/core/latest/x86_64/mirror.list"


HPE_RHEL_7 = "http://downloads.linux.hpe.com/SDR/repo/spp/redhat/7/x86_64/current/"
HPE_CENTOS_7 = "http://downloads.linux.hpe.com/SDR/repo/mcp/CentOS/7/x86_64/current/"

NVIDIA_CUDA_EL8_URL = "https://developer.download.nvidia.com/compute/cuda/repos/rhel8/x86_64/"

MICROSOFT_RHEL8_ADDITIONS = "https://packages.microsoft.com/rhel/8/prod/"

WITH_LOCATION_BASE = "https://harbottle.gitlab.io/harbottle-main/8/x86_64/"
MULTIPLE_CHECKSUMS = "https://packages.rundeck.com/pagerduty/rundeck/rpm_any/rpm_any/x86_64/"
EMPTY_FILELISTS = "https://packages.gitlab.com/gitlab/gitlab-ce/scientific/7/x86_64/"

LOCAL = "http://localhost:8088/repos/centos7"
LOCAL_FILE = "file:///home/vagrant/devel/repos/centos7"

# Content-Encoding: gzip
HASHICORP_RHEL8 = "https://rpm.releases.hashicorp.com/RHEL/8/x86_64/stable/"

RHEL_9_BETA_KICKSTART = "https://cdn.redhat.com/content/beta/rhel9/9/x86_64/appstream/kickstart/"

PERF_SONAR = "http://software.internet2.edu/rpms/el7/x86_64/main/"
CENTREON = "https://yum.centreon.com/standard/21.10/el7/stable/x86_64/"

VMWARE_PHOTON = "https://packages.vmware.com/photon/3.0/photon_updates_3.0_x86_64"

ARTIFACTORY = "https://releases.jfrog.io/artifactory/artifactory-pro-rpms/"

# ==================================================

# RPM_REPO_URL = "http://amazonlinux.us-east-1.amazonaws.com/2/extras/java-openjdk11/latest/x86_64/mirror.list"
# "https://cdn.redhat.com/content/dist/rhel8/8.4/x86_64/baseos/kickstart"
# "https://yum.theforeman.org/releases/2.5/el7/x86_64/"  # FIXTURE_DISTRIBUTION_TREE  "https://packages.broadcom.com/artifactory/saltproject-rpm/"
RPM_REPO_URL = "https://console.redhat.com/api/pulp-content/public-copr-stage/praiskup/test-pulp-cleanup/fedora-rawhide-x86_64/"  # "https://releases.jfrog.io/artifactory/jfrog-rpms/" # "https://packages.grafana.com/oss/rpm/" # "https://fixtures.pulpproject.org/rpm-distribution-tree-empty-root/" # "https://rpms.remirepo.net/enterprise/9/modular/x86_64/"  # "https://cdn.redhat.com/content/dist/rhel/server/6/6.5/x86_64/kickstart/" # CENTOS_8_STREAM_APPSTREAM_URL # "https://www.mercurial-scm.org/release/centos8/"  #"https://download.copr.fedorainfracloud.org/results/audron/dexed/fedora-38-aarch64/" # "https://packages.graylog2.org/repo/el/stable/2.2/x86_64/" # "https://www.keepersecurity.com/kcm/2/el/8/x86_64"
#  # "https://packages.microsoft.com/rhel/8/prod/"  # "https://cdn.redhat.com/content/dist/rhel/workstation/7/7Workstation/x86_64/rhscl/1/os/"  # "https://partha.fedorapeople.org/test-repos/duck-zoo"  # "https://cdn.redhat.com/content/dist/rhel/server/6/6.10/x86_64/kickstart/" # "https://artifacts.elastic.co/packages/7.x/yum/"
PULP_TO_PULP = "http://pulp3-source-fedora36.thinkpad.example.com/pulp/content/rpm_test/"

RPM_REPO_NAME = "test"

try:
    rpm_remote = rpm_remote_api.create(
        {
            "name": RPM_REPO_NAME,
            "url": RPM_REPO_URL,
            "policy": "on_demand",
            "client_cert": open("/src/cpcert/rhcdn.pem", mode="r").read(),
            "client_key": open("/src/cpcert/rhcdn.pem", mode="r").read(),
            "ca_cert": open("/src/cpcert/redhat-uep.pem", mode="r").read(),
            "tls_validation": False,
        }
    )
except Exception:
    pass

try:
    rpm_repo = rpm_repo_api.create(
        {
            "name": RPM_REPO_NAME,
            # 'remote': rpm_remote.pulp_href,
            # 'autopublish': True,
            # 'metadata_signing_service': "/pulp/api/v3/signing-services/4c993760-97e0-4ffd-8bf8-f77d78ed7664/",
            # 'retain_package_versions': 1,
            # 'retain_repo_versions': 1,
            # 'repo_gpgcheck': 1,
            # 'gpgcheck': 1,
            "layout": "flat",
        }
    )
except Exception:
    pass

rpm_remote = rpm_remote_api.list(name=RPM_REPO_NAME).results[0]
rpm_repo = rpm_repo_api.list(name=RPM_REPO_NAME).results[0]

# # ======================
# #         Sync
# ======================

repository_sync_data = RpmRepositorySyncURL(
    remote=rpm_remote.pulp_href,
    sync_policy="mirror_content_only",
    optimize=False,  # skip_types=["treeinfo"]
)

sync_response = rpm_repo_api.sync(
    rpm_repo.pulp_href, repository_sync_data, x_task_diagnostics=["logs"]
)
task = monitor_task(sync_response.task)
time_diff = task.finished_at - task.started_at
print("Sync task HREF: {}".format(task.pulp_href))
print("Sync time: {} seconds".format(time_diff.seconds))

# resync_response = rpm_repo_api.sync(rpm_repo.pulp_href, repository_sync_data)
# task = monitor_task(resync_response.task)
# time_diff = task.finished_at - task.started_at
# print("Sync task HREF: {}".format(task.pulp_href))
# print("Re-sync time: {} seconds".format(time_diff.seconds))


# ======================
#          ACS
# ======================

# acs_refresh = rpm_acs_api.refresh(acs.pulp_href)
# monitor_task_group(acs_refresh.task_group)

# ======================
#      Page Content
# ======================

# page_num = 0
# num_read = 0
# while True:
#     content = rpm_content_api.list(offset=num_read)
#     page = content.results
#     num_read += len(page)
#     print("Showing page {}".format(page_num))
#     page_num += 1
#     if not content.next:
#         break

# ======================
#        Status
# ======================

# import requests
# import urllib
# for i in range(2000):
#     requests.get(urllib.parse.urljoin(url, "/pulp/api/v3/status/"))
#     # status_api.status_read()


# ======================
#        Publish
# # ======================

# publish_response = rpm_publication_api.create({'repository': rpm_repo.pulp_href, 'compression_type': 'zstd'}, x_task_diagnostics=["logs"])
# task = monitor_task(publish_response.task)
# time_diff = task.finished_at - task.started_at
# print("Publish task HREF: {}".format(task.pulp_href))
# print("Publish time: {} seconds".format(time_diff.seconds))

# publication_href = task.created_resources[0]

# publish_response = rpm_publication_api.create({'repository': rpm_repo.pulp_href})
# task = monitor_task(publish_response.task)
# time_diff = task.finished_at - task.started_at
# print("Publish time: {} seconds".format(time_diff.seconds))

# publication_href = task.created_resources[0]

# =======================
#          Prune
# =======================

print("Pruning packages")
params = PrunePackages(repo_hrefs=[rpm_repo.pulp_href], dry_run=False, keep_days=0)
task_group = monitor_task_group(
    rpm_prune_api.prune_packages(params, x_task_diagnostics=["logs"]).task_group
)

for task in task_group.tasks:
    if task.name == "pulp_rpm.app.tasks.prune.prune_repo_packages":
        prune_task = monitor_task(task.pulp_href)
        assert 1 == len(prune_task.progress_reports)
        print("Prune task HREF: {}".format(task.pulp_href))
        print(
            "    {} packages to prune, {} packages pruned".format(
                prune_task.progress_reports[0].total, prune_task.progress_reports[0].done
            )
        )

rpm_repo = rpm_repo_api.read(rpm_repo.pulp_href)
contents = rpm_content_api.list(repository_version=rpm_repo.latest_version_href).results
print(len(contents))

# task = rpm_repo_api.modify(
#     rpm_repo.pulp_href, {"remove_content_units": [content.pulp_href for content in contents]}
# ).task
# monitor_task(task)

# rpm_repo = rpm_repo_api.read(rpm_repo.pulp_href)
# contents = rpm_content_api.list(
#     repository_version=rpm_repo.latest_version_href
# ).results
# print(len(contents))

# =======================
#       Distribute
# =======================

try:
    rpm_distribution = rpm_distributions_api.list(name=RPM_REPO_NAME).results[0]
except IndexError:
    rpm_distribution = rpm_distributions_api.create(
        {
            "base_path": RPM_REPO_NAME,
            "name": RPM_REPO_NAME,
            # "repo_version": rpm_repo.latest_version_href,
            "repository": rpm_repo.pulp_href,
            # "publication": publication_href
        }
    )

# rpm_repo_api.delete(rpm_repo.pulp_href)
