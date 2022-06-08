from gettext import gettext as _

from rest_framework import fields, serializers

from pulpcore.app.models import Content
from pulpcore.app.serializers import ValidateFieldsMixin


class OrphansCleanupSerializer(serializers.Serializer, ValidateFieldsMixin):

    content_hrefs = fields.ListField(
        required=False,
        help_text=_("Will delete specified content and associated Artifacts if they are orphans."),
    )
    orphan_protection_time = serializers.IntegerField(
        help_text=(
            "The time in minutes for how long Pulp will hold orphan Content and Artifacts before "
            "they become candidates for deletion by this orphan cleanup task. This should ideally "
            "be longer than your longest running task otherwise any content created during that "
            "task could be cleaned up before the task finishes. If not specified, a default value "
            "is taken from the setting ORPHAN_PROTECTION_TIME."
        ),
        allow_null=True,
        required=False,
    )

    def validate_content_hrefs(self, value):
        """
        Check that the content_hrefs is not an empty list and contains all valid hrefs.
        Args:
            value (list): The list supplied by the user
        Returns:
            The list of pks (not hrefs) after validation
        Raises:
            ValidationError: If the list is empty or contains invalid hrefs.
        """
        if len(value) == 0:
            raise serializers.ValidationError("Must not be [].")
        from pulpcore.app.viewsets import NamedModelViewSet

        pks_to_return = []
        for href in value:
            pks_to_return.append(NamedModelViewSet.get_resource(href, Content).pk)

        return pks_to_return
