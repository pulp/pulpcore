from datetime import datetime
from gettext import gettext as _
from logging import getLogger

from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.models import CreatedResource
from pulpcore.app.serializers import ArtifactUploadSerializer
from pulpcore.tasking.util import get_url

log = getLogger(__name__)


def commit(upload_id, sha256):
    """
    Commit the upload and mark it as completed.

    Commit a :class:`~pulpcore.app.models.Upload`

    Args:
        upload_id (int): The upload primary key
        sha256 (str): The checksum for the uploaded file

    """
    try:
        upload = models.Upload.objects.get(pk=upload_id)
    except models.Upload.DoesNotExist:
        log.info(_('The upload was not found. Nothing to do.'))
        return

    log.info(_('Commiting the upload %(i)d and mark it as completed'), {'i': upload_id})

    if not sha256:
        raise serializers.ValidationError(_("Checksum not supplied."))

    upload.completed = datetime.now()
    upload.save()

    data = {'upload': get_url(upload), 'sha256': sha256}
    serializer = ArtifactUploadSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    artifact = serializer.save()

    resource = CreatedResource(content_object=artifact)
    resource.save()
