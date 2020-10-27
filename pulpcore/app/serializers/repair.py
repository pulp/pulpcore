from gettext import gettext as _

from rest_framework import fields, serializers

from pulpcore.app.serializers import ValidateFieldsMixin  # noqa


class RepairSerializer(serializers.Serializer, ValidateFieldsMixin):
    verify_checksums = fields.BooleanField(
        required=False,
        default=True,
        help_text=_(
            "Will verify that the checksum of all stored files matches what saved in the "
            "database. Otherwise only the existence of the files will be checked. Enabled "
            "by default"
        ),
    )
