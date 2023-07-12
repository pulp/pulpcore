from gettext import gettext as _

from django.conf import settings
from rest_framework import fields, serializers

from pulpcore.app.models import Content
from pulpcore.app.serializers import ValidateFieldsMixin
from pulpcore.app.tasks.base import general_serializer_task
from pulpcore.tasking.tasks import dispatch


class OrphansCleanupSerializer(serializers.Serializer, ValidateFieldsMixin):
    content_hrefs = fields.ListField(
        required=False,
        help_text=_("Will delete specified content and associated Artifacts if they are orphans."),
        write_only=True,
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
        write_only=True,
    )
    deleted_artifacts = serializers.IntegerField(
        read_only=True,
    )
    deleted_content = serializers.IntegerField(
        read_only=True,
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

    def validate_orphan_protection_time(self, value):
        if value is None:
            value = settings.ORPHAN_PROTECTION_TIME
        return value

    def resources(self):
        uri = "/api/v3/orphans/cleanup/"
        if settings.DOMAIN_ENABLED:
            request = self.context["request"]
            uri = f"/{request.pulp_domain.name}{uri}"
        return [uri], None

    def cleanup(self, validated_data):
        assert "task" in self.context

        from pulpcore.app.tasks.orphan import orphan_cleanup

        # TODO Think about moving the implementation here.

        orphan_cleanup(**validated_data)
        return {
            "deleted_" + pr.code.split(".")[1]: pr.done
            for pr in self.context["task"].progress_reports.all()
        }

    def dispatch(self, method):
        serializer_id = self.__class__.__module__ + ":" + self.__class__.__qualname__
        exclusive_resources, shared_resources = self.resources()
        return dispatch(
            general_serializer_task,
            exclusive_resources=exclusive_resources,
            shared_resources=shared_resources,
            kwargs={
                "serializer_id": serializer_id,
                "method": method,
                "data": self.initial_data,
                "partial": self.partial,
            },
        )
