from gettext import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.serializers import ValidationError

from pulpcore.app import tasks
from pulpcore.app.models import Content, RepositoryVersion
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    RepositoryAddRemoveContentSerializer,
)
from pulpcore.app.viewsets import NamedModelViewSet
from pulpcore.tasking.tasks import dispatch


__all__ = ["ModifyRepositoryActionMixin"]


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
        add_content_units = {}
        remove_content_units = {}

        repository = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if "base_version" in request.data:
            base_version_pk = self.get_resource(request.data["base_version"], RepositoryVersion).pk
        else:
            base_version_pk = None

        if "add_content_units" in request.data:
            for url in request.data["add_content_units"]:
                add_content_units[NamedModelViewSet.extract_pk(url)] = url

            content_units_pks = set(add_content_units.keys())
            existing_content_units = Content.objects.filter(pk__in=content_units_pks)
            existing_content_units.touch()

            self.verify_content_units(existing_content_units, add_content_units)

            add_content_units = list(add_content_units.keys())

        if "remove_content_units" in request.data:
            if "*" in request.data["remove_content_units"]:
                remove_content_units = ["*"]
            else:
                for url in request.data["remove_content_units"]:
                    remove_content_units[NamedModelViewSet.extract_pk(url)] = url
                content_units_pks = set(remove_content_units.keys())
                existing_content_units = Content.objects.filter(pk__in=content_units_pks)
                self.verify_content_units(existing_content_units, remove_content_units)
                remove_content_units = list(remove_content_units.keys())

        task = dispatch(
            tasks.repository.add_and_remove,
            exclusive_resources=[repository],
            kwargs={
                "repository_pk": pk,
                "base_version_pk": base_version_pk,
                "add_content_units": add_content_units,
                "remove_content_units": remove_content_units,
            },
        )
        return OperationPostponedResponse(task, request)

    def verify_content_units(self, content_units, all_content_units):
        """Verify referenced content units."""
        existing_content_units_pks = content_units.values_list("pk", flat=True)
        existing_content_units_pks = {str(pk) for pk in existing_content_units_pks}

        missing_pks = set(all_content_units.keys()) - existing_content_units_pks
        if missing_pks:
            missing_hrefs = [all_content_units[pk] for pk in missing_pks]
            raise ValidationError(
                _("Could not find the following content units: {}").format(missing_hrefs)
            )
