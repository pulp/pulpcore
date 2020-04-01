import os

from import_export import resources
from pulpcore.app.models.content import (
    Artifact,
    Content,
    ContentArtifact,
)
from pulpcore.app.models.repository import (
    Repository,
    RepositoryVersion,
)


class RepositoryResource(resources.ModelResource):
    class Meta:
        model = Repository


class RepositoryVersionResource(resources.ModelResource):
    class Meta:
        model = RepositoryVersion


class ArtifactResource(resources.ModelResource):
    class Meta:
        model = Artifact


class ContentResource(resources.ModelResource):
    class Meta:
        model = Content


class ContentArtifactResource(resources.ModelResource):
    class Meta:
        model = ContentArtifact


def export_content(export, repository_version):
        dest = os.path.join(export.destination_dir, 'repository-{}-{}'.format(str(repository_version.repository.pulp_id), repository_version.number))
        try:
            os.makedirs(dest)
        except FileExistsError:
            pass

        resource = ArtifactResource()
        queryset = repository_version.artifacts
        dataset = resource.export(queryset)
        file = os.path.join(dest, 'artifactresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)

        resource = ContentResource()
        queryset = repository_version.content
        dataset = resource.export(queryset)
        file = os.path.join(dest, 'contentresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)

        resource = ContentArtifactResource()
        queryset = ContentArtifact.objects.filter(content__in=repository_version.content)
        dataset = resource.export(queryset)
        file = os.path.join(dest, 'contentartifactresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)

        resource = RepositoryVersionResource()
        queryset = RepositoryVersion.objects.filter(pulp_id=repository_version.pulp_id)
        dataset = resource.export(queryset)
        file = os.path.join(dest, 'repositoryversionresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)

        resource = RepositoryResource()
        queryset = Repository.objects.filter(pk__in=export.exporter.repositories.all())
        dataset = resource.export(queryset)
        file = os.path.join(export.destination_dir, 'repositoryresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)