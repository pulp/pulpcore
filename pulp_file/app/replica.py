from pulpcore.plugin.replica import Replicator

from pulp_glue.file.context import (
    PulpFileDistributionContext,
    PulpFilePublicationContext,
    PulpFileRepositoryContext,
)

from pulp_file.app.models import FileDistribution, FileRemote, FileRepository
from pulp_file.app.tasks import synchronize as file_synchronize


class FileReplicator(Replicator):
    repository_ctx_cls = PulpFileRepositoryContext
    distribution_ctx_cls = PulpFileDistributionContext
    publication_ctx_cls = PulpFilePublicationContext
    app_label = "file"
    remote_model_cls = FileRemote
    repository_model_cls = FileRepository
    distribution_model_cls = FileDistribution
    distribution_serializer_name = "FileDistributionSerializer"
    repository_serializer_name = "FileRepositorySerializer"
    remote_serializer_name = "FileRemoteSerializer"
    sync_task = file_synchronize

    def url(self, upstream_distribution):
        # Check if a distribution is repository or publication based
        if upstream_distribution["repository"]:
            manifest = self.repository_ctx_cls(
                self.pulp_ctx, upstream_distribution["repository"]
            ).entity["manifest"]
        elif upstream_distribution["publication"]:
            manifest = self.publication_ctx_cls(
                self.pulp_ctx, upstream_distribution["publication"]
            ).entity["manifest"]
        else:
            # This distribution doesn't serve any content
            return None

        return f"{upstream_distribution['base_url']}{manifest}"

    def repository_extra_fields(self, remote):
        return dict(manifest=remote.url.split("/")[-1], autopublish=True)

    def sync_params(self, repository, remote):
        return dict(
            remote_pk=str(remote.pk),
            repository_pk=str(repository.pk),
            mirror=True,
        )


REPLICATION_ORDER = [FileReplicator]
