from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from pulpcore.app.models import (
    BaseModel,
    MasterModel,
)
from .repository import Repository


class Import(BaseModel):
    """
    A model that represents imports into Pulp.

    Fields:
        params (models.JSONField): A set of parameters used to run the import

    Relations:
        task (models.ForeignKey): The Task that ran the import
        importer (models.ForeignKey): The Importer that imported the export
    """

    params = models.JSONField(null=True)
    task = models.ForeignKey("Task", on_delete=models.PROTECT)
    importer = models.ForeignKey("Importer", on_delete=models.CASCADE)


class Importer(MasterModel):
    """
    A base model that provides logic to import data into Pulp.

    Can be extended by plugins to provide import functionality.

    Fields:
        name (models.TextField): The importer unique name.
    """

    name = models.TextField(db_index=True, unique=True)


class PulpImporter(Importer):
    """
    A model that can be used to import exports from other Pulp instances.
    """

    TYPE = "pulp"

    @property
    def repo_mapping(self):
        return {repo.source_repo: repo.repository.name for repo in self.repo_map.all()}

    @repo_mapping.setter
    def repo_mapping(self, mapping):
        self.repo_map.all().delete()
        failed_repos = []
        # Process a mapping to find the destinations that map to the sources
        # Record all failing destinations to report to the user.
        # Only create the mappings if *everything* worked - otherweise, fail with error.
        the_map = {}
        for source, repo_name in mapping.items():
            try:
                repo = Repository.objects.get(name=repo_name)
                the_map[source] = repo
            except ObjectDoesNotExist:
                failed_repos.append(repo_name)
                continue

        if failed_repos:  # We had a failure - report and leave
            raise ObjectDoesNotExist(f"names: {str(failed_repos)}")

        # Everything worked - create the mapping
        for source, repo in the_map.items():
            self.repo_map.create(source_repo=source, repository=repo)

    class Meta:
        default_related_name = "%(app_label)s_pulp_importer"


class PulpImporterRepository(BaseModel):
    """
    A model that maps repo names in an export to repos in Pulp.

    Fields:
        source_repo (models.TextField): The name of the repo in the export

    Relations:
        pulp_importer (models.ForeignKey): The associated Pulp importer
        repository (models.ForeignKey): The repository in Pulp
    """

    source_repo = models.TextField()
    pulp_importer = models.ForeignKey(
        PulpImporter, related_name="repo_map", on_delete=models.CASCADE
    )
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)


class PulpImport(Import):
    """A model that represents imports into Pulp from another Pulp instance."""

    class Meta:
        default_related_name = "%(app_label)s_pulp_export"
