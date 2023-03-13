import platform
from pkg_resources import get_distribution
import sys

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import UpstreamPulp, TaskGroup
from pulpcore.app.replica import ReplicaContext
from pulpcore.app.util import get_domain

from pulp_glue.common import __version__ as pulp_glue_version


def user_agent():
    """
    Produce a User-Agent string to identify Pulp and relevant system info.
    """
    pulp_version = get_distribution("pulpcore").version
    python = "{} {}.{}.{}-{}{}".format(sys.implementation.name, *sys.version_info)
    uname = platform.uname()
    system = f"{uname.system} {uname.machine}"
    return f"pulpcore/{pulp_version} ({python}, {system}) (pulp-glue {pulp_glue_version})"


def replicate_distributions(server_pk):
    domain = get_domain()
    server = UpstreamPulp.objects.get(pk=server_pk)
    api_kwargs = dict(
        base_url=server.base_url,
        username=server.username,
        password=server.password,
        user_agent=user_agent(),
    )
    ctx = ReplicaContext(
        api_root=server.api_root,
        api_kwargs=api_kwargs,
        format="json",
        background_tasks=True,
        timeout=0,
        domain=server.domain,
    )
    task_group = TaskGroup.current()
    supported_replicators = []
    # Load all the available replicators
    for config in pulp_plugin_configs():
        if config.replicator_classes:
            for replicator_class in config.replicator_classes:
                supported_replicators.append(replicator_class(ctx, task_group))

    for replicator in supported_replicators:
        distros = replicator.upstream_distributions(labels=server.pulp_label_select)
        distro_names = []
        for distro in distros:
            # Create remote
            remote = replicator.create_or_update_remote(upstream_distribution=distro)
            if not remote:
                # The upstream distribution is not serving any content, cleanup an existing local
                # distribution
                try:
                    local_distro = replicator.distribution_model.objects.get(
                        name=distro["name"], pulp_domain=domain
                    )
                    local_distro.repository = None
                    local_distro.publication = None
                    local_distro.save()
                    continue
                except replicator.distribution_model.DoesNotExist:
                    continue
            # Check if there is already a repository
            repository = replicator.create_or_update_repository(remote=remote)

            # Dispatch a sync task
            replicator.sync(repository, remote)

            # Get or create a distribution
            replicator.create_or_update_distribution(repository, distro)

            # Add name to the list of known distribution names
            distro_names.append(distro["name"])

        replicator.remove_missing(distro_names)
        task_group.finish()
