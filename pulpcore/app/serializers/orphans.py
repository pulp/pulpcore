from gettext import gettext as _

from rest_framework import fields, serializers

from pulpcore.app.models import Content
from pulpcore.app.serializers import ValidateFieldsMixin


class OrphansCleanupSerializer(serializers.Serializer, ValidateFieldsMixin):

    content_hrefs = fields.ListField(
        required=False,
        help_text=_("Will delete specified content and associated Artifacts if they are orphans."),
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
