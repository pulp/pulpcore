from gettext import gettext as _

from django_filters.rest_framework import filters

from rest_framework import mixins
from rest_framework.response import Response


from pulpcore.app.models import SharedAttributeManager
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    ManagedResourceSerializer,
    ManagedResourceExistsSerializer,
    SharedAttributeManagerSerializer,
    AsyncOperationResponseSerializer,
)
from pulpcore.app.viewsets import (
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.custom_filters import ManagedEntitiesFilter
from pulpcore.app import tasks
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.serializers import ValidationError

from pulpcore.plugin.tasking import dispatch


class SharedAttributeManagerFilter(BaseFilterSet):
    """
    Filter for SharedAttributeManager.

    You can look for SAMs by name, or by "manages this HREF".
    """

    name = filters.CharFilter()
    managed_entities = ManagedEntitiesFilter()

    class Meta:
        model = SharedAttributeManager
        fields = {
            "name": ["contains"],
            "managed_entities": ["exact"],
        }


class SharedAttributeManagerViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
):
    """
    ViewSet for SharedAttributeManager.

    NOTE: This API endpoint is in "tech preview" and subject to change
    """

    queryset = SharedAttributeManager.objects.all()
    endpoint_name = "shared-attribute-managers"
    filterset_class = SharedAttributeManagerFilter
    serializer_class = SharedAttributeManagerSerializer
    ordering = "-pulp_created"

    @extend_schema(
        description=_(
            "Trigger an asynchronous task to apply managed attributes to managed entities."
        ),
        summary="Apply managed-attributes",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def apply(self, request, *args, **kwargs):
        """
        Dispatches a task to apply changes to all managed entities.
        """
        sam = self.get_object()
        errs = []
        if not sam.managed_entities:
            errs.append(_("No entities are being managed."))

        if not (sam.managed_attributes or sam.managed_sensitive_attributes):
            errs.append(_("No attributes are being managed."))

        if errs:
            raise ValidationError(",".join(errs))

        # Make sure we lock all the entities we may be updating in the "entities" list
        locks = [sam, *sam.managed_entities]
        result = dispatch(
            tasks.update_managed_entities,
            exclusive_resources=locks,
            kwargs={"sam_pk": str(sam.pk)},
        )
        return OperationPostponedResponse(result, request)

    @extend_schema(
        description=_("Add a specified entity to be managed, and update its attributes."),
        summary=_("Add entity to be managed."),
        request=ManagedResourceExistsSerializer,
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def add(self, request, *args, **kwargs):
        """
        Dispatches a task to add, and apply changes to, a newly-managed entity.

        Returns a task, since we don't know how many things need to be managed or how long
        making the changes might take.
        """
        serializer = ManagedResourceExistsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_href = serializer.validated_data.get("entity_href", None)

        sam = self.get_object()
        if entity_href in sam.managed_entities:
            raise ValidationError(_("Entity {} already being managed.".format(entity_href)))

        result = dispatch(
            tasks.add_entity,
            exclusive_resources=[sam, entity_href],
            kwargs={"sam_pk": str(sam.pk), "entity_href": entity_href},
        )
        return OperationPostponedResponse(result, request)

    @extend_schema(
        description=_("Remove an entity from the list being managed."),
        request=ManagedResourceSerializer,
        summary=_("Remove entity from manager."),
        responses={200: Response},
    )
    @action(detail=True, methods=["post"])
    def remove(self, request, *args, **kwargs):
        """
        Dispatches a task to remove an entity from the to-be-managed list.

        Synchronous, since this only removes a list-element.
        """
        serializer = ManagedResourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entity_href = serializer.validated_data.get("entity_href", None)

        sam = self.get_object()

        if entity_href in sam.managed_entities:
            sam.managed_entities.remove(entity_href)
            sam.save()
            return Response(_("Removed {} from managed entities.".format(entity_href)))
        else:
            raise ValidationError(_("Entity {} not being managed.".format(entity_href)))
