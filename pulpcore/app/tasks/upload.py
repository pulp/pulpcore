from gettext import gettext as _
from logging import getLogger
from tempfile import NamedTemporaryFile

from django.core.files import File

from pulpcore.app import files, models
from pulpcore.app.models import CreatedResource
from pulpcore.app.serializers import ArtifactSerializer

log = getLogger(__name__)


def commit(upload_id, sha256):
    """
    Commit the upload and turn it into an artifact.

    Args:
        upload_id (int): The upload primary key
        sha256 (str): The checksum for the uploaded file
    """
    try:
        upload = models.Upload.objects.get(pk=upload_id)
    except models.Upload.DoesNotExist:
        log.info(_("The upload was not found. Nothing to do."))
        return

    chunks = models.UploadChunk.objects.filter(upload=upload).order_by("offset")
    with NamedTemporaryFile("ab") as temp_file:
        for chunk in chunks:
            temp_file.write(chunk.file.read())
            chunk.file.close()
        temp_file.flush()

        file = files.PulpTemporaryUploadedFile.from_file(File(open(temp_file.name, "rb")))

    data = {"file": file, "sha256": sha256}
    serializer = ArtifactSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    artifact = serializer.save()

    resource = CreatedResource(content_object=artifact)
    resource.save()

    # delete the upload since it can't be reused to create another artifact
    upload.delete()
