from django.conf import settings
from django.db.models import Model
import logging

from pulp_glue.common.context import PulpContext
from pulpcore.tasking.tasks import dispatch
from pulpcore.app.tasks.base import (
    general_update,
    general_create,
    general_multi_delete,
)
from pulpcore.plugin.util import get_url, get_domain

_logger = logging.getLogger(__name__)


class ReplicaContext(PulpContext):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.out_buf = ""
        self.err_buf = ""

    def echo(self, message: str, nl: bool = True, err: bool = False) -> None:
        if err:
            self.err_buf += message
            if nl:
                _logger.warn("{}", self.err_buf)
                self.err_buf = ""
        else:
            self.out_buf += message
            if nl:
                _logger.info("{}", self.out_buf)
                self.out_buf = ""


class Replicator:
    distribution_ctx_cls = None
    repository_ctx_cls = None
    publication_ctx_cls = None
    remote_model_cls = None
    repository_model_cls = None
    distribution_model_cls = None
    distribution_serializer_name = None
    repository_serializer_name = None
    remote_serializer_name = None
    app_label = None
    sync_task = None

    def __init__(self, pulp_ctx, task_group, tls_settings):
        """
        :param pulp_ctx: PulpReplicaContext
        :param task_group: TaskGroup
        :param ca_cert: str
        """
        self.pulp_ctx = pulp_ctx
        self.task_group = task_group
        self.tls_settings = tls_settings
        self.domain = get_domain()
        uri = "/api/v3/distributions/"
        # TODO check and compare this to distribution locking on the distribution viewset.
        if settings.DOMAIN_ENABLED:
            uri = f"/{self.domain.name}{uri}"
        self.distros_uri = uri

    @staticmethod
    def needs_update(fields_dict, model_instance):
        """
        Compares a Model instance's attributes against a dictionary where keys are attribute
        names and values are expected values.
        """
        needs_update = False
        for field_name, value in fields_dict.items():
            if isinstance(getattr(model_instance, field_name), Model):
                if get_url(getattr(model_instance, field_name)) != value:
                    needs_update = True
            elif getattr(model_instance, field_name) != value:
                needs_update = True
        return needs_update

    def upstream_distributions(self, labels=None):
        if labels:
            params = {"pulp_label_select": labels}
        else:
            params = {}
        offset = 0
        list_size = 100
        while True:
            distributions = self.distribution_ctx_cls(self.pulp_ctx).list(list_size, offset, params)
            for distro in distributions:
                yield distro
            if len(distributions) < list_size:
                break
            offset += list_size

    def url(self, upstream_distribution):
        return upstream_distribution["base_url"]

    def remote_extra_fields(self, upstream_distribution):
        return {}

    def create_or_update_remote(self, upstream_distribution):
        if not upstream_distribution.get("repository") and not upstream_distribution.get(
            "publication"
        ):
            return None
        url = self.url(upstream_distribution)
        remote_fields_dict = {"url": url}
        remote_fields_dict.update(self.tls_settings)
        remote_fields_dict.update(self.remote_extra_fields(upstream_distribution))

        # Check if there is a remote pointing to this distribution
        try:
            remote = self.remote_model_cls.objects.get(
                name=upstream_distribution["name"], pulp_domain=self.domain
            )
            needs_update = self.needs_update(remote_fields_dict, remote)
            if needs_update:
                dispatch(
                    general_update,
                    task_group=self.task_group,
                    exclusive_resources=[remote],
                    args=(remote.pk, self.app_label, self.remote_serializer_name),
                    kwargs={"data": remote_fields_dict, "partial": True},
                )
        except self.remote_model_cls.DoesNotExist:
            # Create the remote
            remote = self.remote_model_cls(name=upstream_distribution["name"], **remote_fields_dict)
            remote.save()

        return remote

    def repository_extra_fields(self, remote):
        return {}

    def create_or_update_repository(self, remote):
        try:
            repository = self.repository_model_cls.objects.get(
                name=remote.name, pulp_domain=self.domain
            )
            repo_fields_dict = self.repository_extra_fields(remote)
            needs_update = self.needs_update(repo_fields_dict, repository)
            if needs_update:
                dispatch(
                    general_update,
                    task_group=self.task_group,
                    exclusive_resources=[repository],
                    args=(repository.pk, self.app_label, self.repository_serializer_name),
                    kwargs={"data": repo_fields_dict, "partial": True},
                )
        except self.repository_model_cls.DoesNotExist:
            repository = self.repository_model_cls(
                name=remote.name, **self.repository_extra_fields(remote)
            )
            repository.save()
        return repository

    def distribution_data(self, repository, upstream_distribution):
        """
        Return the fields that need to be updated/cleared on distributions for idempotence.
        """
        return {
            "repository": get_url(repository),
            "publication": None,
            "base_path": upstream_distribution["base_path"],
        }

    def create_or_update_distribution(self, repository, upstream_distribution):
        distribution_data = self.distribution_data(repository, upstream_distribution)
        try:
            distro = self.distribution_model_cls.objects.get(
                name=upstream_distribution["name"], pulp_domain=self.domain
            )
            # Check that the distribution has the right repository associated
            needs_update = self.needs_update(distribution_data, distro)
            if needs_update:
                # Update the distribution
                dispatch(
                    general_update,
                    task_group=self.task_group,
                    shared_resources=[repository],
                    exclusive_resources=[self.distros_uri],
                    args=(distro.pk, self.app_label, self.distribution_serializer_name),
                    kwargs={
                        "data": distribution_data,
                        "partial": True,
                    },
                )
        except self.distribution_model_cls.DoesNotExist:
            # Dispatch a task to create the distribution
            distribution_data["name"] = upstream_distribution["name"]
            dispatch(
                general_create,
                task_group=self.task_group,
                shared_resources=[repository],
                exclusive_resources=[self.distros_uri],
                args=(self.app_label, self.distribution_serializer_name),
                kwargs={"data": distribution_data},
            )

    def sync_params(self, repository, remote):
        """This method returns a dict that will be passed as kwargs to the sync task."""
        raise NotImplementedError("Each replicator must supply its own sync params.")

    def sync(self, repository, remote):
        dispatch(
            self.sync_task,
            task_group=self.task_group,
            shared_resources=[remote],
            exclusive_resources=[repository],
            kwargs=self.sync_params(repository, remote),
        )

    def remove_missing(self, names):
        # Remove all distributions with names not present in the list of names
        # Perform this in an extra task, because we hold a big lock here.
        distribution_ids = [
            (distribution.pk, self.app_label, self.distribution_serializer_name)
            for distribution in self.distribution_model_cls.objects.filter(
                pulp_domain=self.domain
            ).exclude(name__in=names)
        ]
        if distribution_ids:
            dispatch(
                general_multi_delete,
                task_group=self.task_group,
                exclusive_resources=[self.distros_uri],
                args=(distribution_ids,),
            )

        # Remove all the repositories and remotes of the missing distributions
        repositories = list(
            self.repository_model_cls.objects.filter(pulp_domain=self.domain).exclude(
                name__in=names
            )
        )
        repository_ids = [
            (repo.pk, self.app_label, self.repository_serializer_name) for repo in repositories
        ]

        remotes = list(
            self.remote_model_cls.objects.filter(pulp_domain=self.domain).exclude(name__in=names)
        )
        remote_ids = [
            (remote.pk, self.app_label, self.remote_serializer_name) for remote in remotes
        ]

        if repository_ids or remote_ids:
            dispatch(
                general_multi_delete,
                task_group=self.task_group,
                exclusive_resources=repositories + remotes,
                args=(repository_ids + remote_ids,),
            )
