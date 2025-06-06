import os
import platform
import sys
from tempfile import NamedTemporaryFile

from django.db.models import Min

from pulpcore.constants import TASK_STATES
from pulpcore.app.apps import pulp_plugin_configs, PulpAppConfig
from pulpcore.app.models import UpstreamPulp, Task, TaskGroup
from pulpcore.app.replica import ReplicaContext
from pulpcore.tasking.tasks import dispatch

from pulp_glue.common import __version__ as pulp_glue_version
from pulp_glue.common.context import PluginRequirement


def user_agent():
    """
    Produce a User-Agent string to identify Pulp and relevant system info.
    """
    pulp_version = PulpAppConfig.version
    python = "{} {}.{}.{}-{}{}".format(sys.implementation.name, *sys.version_info)
    uname = platform.uname()
    system = f"{uname.system} {uname.machine}"
    return f"pulpcore/{pulp_version} ({python}, {system}) (pulp-glue {pulp_glue_version})"


def replicate_distributions(server_pk):
    server = UpstreamPulp.objects.get(pk=server_pk)

    # Write out temporary files related to SSL
    ssl_files = {}
    for key in ["ca_cert", "client_cert", "client_key"]:
        if value := getattr(server, key):
            f = NamedTemporaryFile(dir=".")
            f.write(bytes(value, "utf-8"))
            f.flush()
            ssl_files[key] = f.name

    if "ca_cert" in ssl_files:
        os.environ["PULP_CA_BUNDLE"] = ssl_files["ca_cert"]

    api_kwargs = dict(
        base_url=server.base_url,
        username=server.username,
        password=server.password,
        user_agent=user_agent(),
        validate_certs=server.tls_validation,
        cert=ssl_files.get("client_cert"),
        key=ssl_files.get("client_key"),
    )

    ctx = ReplicaContext(
        api_root=server.api_root,
        api_kwargs=api_kwargs,
        background_tasks=True,
        timeout=0,
        domain=server.domain,
    )

    tls_settings = {
        "ca_cert": server.ca_cert,
        "tls_validation": server.tls_validation,
        "client_cert": server.client_cert,
        "client_key": server.client_key,
    }

    task_group = TaskGroup.current()
    supported_replicators = []
    # Load all the available replicators
    for config in pulp_plugin_configs():
        if config.replicator_classes:
            for replicator_class in config.replicator_classes:
                req = PluginRequirement(config.label, specifier=replicator_class.required_version)
                if ctx.has_plugin(req):
                    replicator = replicator_class(ctx, task_group, tls_settings, server)
                    supported_replicators.append(replicator)

    for replicator in supported_replicators:
        distros = replicator.upstream_distributions(q=server.q_select)
        distro_names = []
        for distro in distros:
            # Create remote
            remote = replicator.create_or_update_remote(upstream_distribution=distro)
            if not remote:
                # The upstream distribution is not serving any content,
                # let if fall through the cracks and be cleanup below.
                continue
            # Check if there is already a repository
            repository = replicator.create_or_update_repository(remote=remote)
            if not repository:
                # No update occured because server.policy==LABELED and there was
                # an already existing local repository with the same name
                continue

            # Dispatch a sync task if needed
            if replicator.requires_syncing(distro):
                replicator.sync(repository, remote)

            # Get or create a distribution
            replicator.create_or_update_distribution(repository, distro)

            # Add name to the list of known distribution names
            distro_names.append(distro["name"])

        replicator.remove_missing(distro_names)

    dispatch(
        finalize_replication,
        task_group=task_group,
        exclusive_resources=[server],
        args=[server.pk],
    )


def finalize_replication(server_pk):
    task = Task.current()
    task_group = TaskGroup.current()
    server = UpstreamPulp.objects.get(pk=server_pk)
    if task_group.tasks.exclude(pk=task.pk).exclude(state=TASK_STATES.COMPLETED).exists():
        raise Exception("Replication failed.")

    # Record timestamp of last successful replication.
    started_at = task_group.tasks.aggregate(Min("started_at"))["started_at__min"]
    server.set_last_replication_timestamp(started_at)
