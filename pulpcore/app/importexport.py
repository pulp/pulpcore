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
        dest = os.path.join(export.destination_dir, 'repository-{}'.format(str(repository_version.pulp_id)))
        try:
            os.makedirs(dest)
        except FileExistsError:
            pass

        resource = ArtifactResource()
        dataset = resource.export()
        file = os.path.join(dest, 'artifactresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)
        resource = ContentResource()
        dataset = resource.export()
        file = os.path.join(dest, 'contentresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)
        resource = ContentArtifactResource()
        dataset = resource.export()
        file = os.path.join(dest, 'contentartifactresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)
        resource = RepositoryResource()
        dataset = resource.export()
        file = os.path.join(dest, 'repositoryresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)
        resource = RepositoryVersionResource()
        dataset = resource.export()
        file = os.path.join(dest, 'repositoryversionresource.json')
        with open(file, "w") as f:
            f.write(dataset.json)