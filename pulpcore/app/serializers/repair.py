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


class DataRepair7272Serializer(serializers.Serializer, ValidateFieldsMixin):
    dry_run = fields.BooleanField(
        required=False,
        default=False,
        help_text=_(
            "If true, only report issues without fixing them. If false (default), "
            "repair the detected issues."
        ),
    )


class DataRepair7465Serializer(serializers.Serializer, ValidateFieldsMixin):
    dry_run = fields.BooleanField(
        required=False,
        default=False,
        help_text=_(
            "If true, only report issues without fixing them. If false (default), "
            "repair the detected issues."
        ),
    )
