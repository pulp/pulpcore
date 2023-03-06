from gettext import gettext as _

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.serializers import ValidationError

from pulpcore.app import tasks
from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.models import RepositoryVersion
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    RepositoryAddRemoveContentSerializer,
)
from pulpcore.tasking.tasks import dispatch


__all__ = ["ModifyRepositoryActionMixin", "raise_for_unknown_content_units"]


class ModifyRepositoryActionMixin:
    @extend_schema(
        description="Trigger an asynchronous task to create a new repository version.",
        summary="Modify Repository Content",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=RepositoryAddRemoveContentSerializer)
    def modify(self, request, pk):
        """
        Queues a task that creates a new RepositoryVersion by adding and removing content units
        """
        repository = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if "base_version" in request.data:
            base_version_pk = self.get_resource(request.data["base_version"], RepositoryVersion).pk
        else:
            base_version_pk = None

        task = dispatch(
            tasks.repository.add_and_remove,
            exclusive_resources=[repository],
            kwargs={
                "repository_pk": pk,
                "base_version_pk": base_version_pk,
                "add_content_units": serializer.validated_data.get("add_content_units", []),
                "remove_content_units": serializer.validated_data.get("remove_content_units", []),
            },
        )
        return OperationPostponedResponse(task, request)


def raise_for_unknown_content_units(existing_content_units, content_units_pks_hrefs):
    """Verify if all the specified content units were found in the database.

    Args:
        existing_content_units (pulpcore.plugin.models.Content): Content filtered by
            specified_content_units.
        content_units_pks_hrefs (dict): An original dictionary of pk-href pairs that
            are used for the verification.
    Raises:
        ValidationError: If some of the referenced content units are not present in the database
    """
    deprecation_logger.warning(
        "pulpcore.plugin.actions.raise_for_unknown_content_units() is deprecated and will be "
        "removed in pulpcore==3.25; use pulpcore.plugin.util.raise_for_unknown_content_units()."
    )
    existing_content_units_pks = existing_content_units.values_list("pk", flat=True)
    existing_content_units_pks = set(map(str, existing_content_units_pks))

    missing_pks = set(content_units_pks_hrefs.keys()) - existing_content_units_pks
    if missing_pks:
        missing_hrefs = [content_units_pks_hrefs[pk] for pk in missing_pks]
        raise ValidationError(
            _("Could not find the following content units: {}").format(missing_hrefs)
        )
