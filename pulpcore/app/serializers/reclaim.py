from gettext import gettext as _

from rest_framework import fields, serializers

from pulpcore.app.models import Repository

from pulpcore.app.serializers import RepositoryVersionRelatedField, ValidateFieldsMixin
from pulpcore.app.util import get_domain


class ReclaimSpaceSerializer(serializers.Serializer, ValidateFieldsMixin):
    """
    Serializer for reclaim disk space operation.
    """

    repo_hrefs = fields.ListField(
        required=True,
        help_text=_(
            "Will reclaim space for the specified list of repos. Use ['*'] to specify all repos."
        ),
    )
    repo_versions_keeplist = RepositoryVersionRelatedField(
        help_text=_("Will exclude repo versions from space reclaim."),
        many=True,
        required=False,
    )

    def validate_repo_hrefs(self, value):
        """
        Check that the repo_hrefs is not an empty list and contains all valid hrefs.
        Args:
            value (list): The list supplied by the user
        Returns:
            The list of Repositories after validation
        Raises:
            ValidationError: If the list is empty or contains invalid hrefs.
        """
        if len(value) == 0:
            raise serializers.ValidationError("Must not be [].")
        if "*" in value:
            if len(value) != 1:
                raise serializers.ValidationError("Can not specify other HREFs when using '*'")
            return Repository.objects.filter(pulp_domain=get_domain())

        from pulpcore.app.viewsets import NamedModelViewSet

        hrefs_to_return = []
        for href in value:
            hrefs_to_return.append(NamedModelViewSet.get_resource(href, Repository))

        return hrefs_to_return
