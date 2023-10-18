from pulpcore.plugin.importexport import BaseContentResource
from pulpcore.plugin.modelresources import RepositoryResource
from pulp_file.app.models import FileContent, FileRepository


class FileContentResource(BaseContentResource):
    """
    Resource for import/export of file_filecontent entities
    """

    def set_up_queryset(self):
        """
        :return: FileContents specific to a specified repo-version.
        """
        return FileContent.objects.filter(pk__in=self.repo_version.content)

    class Meta:
        model = FileContent
        import_id_fields = model.natural_key_fields()


class FileRepositoryResource(RepositoryResource):
    """
    A resource for importing/exporting file repository entities
    """

    def set_up_queryset(self):
        """
        :return: A queryset containing one repository that will be exported.
        """
        return FileRepository.objects.filter(pk=self.repo_version.repository)

    class Meta:
        model = FileRepository


IMPORT_ORDER = [FileContentResource, FileRepositoryResource]
