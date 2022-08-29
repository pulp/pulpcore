from logging import getLogger
from rest_framework.exceptions import ValidationError

from pulpcore.app import util
from pulpcore.app.models import SharedAttributeManager, Task
from pulpcore.app.models.progress import ProgressReport

log = getLogger(__name__)


def add_entity(sam_pk, entity_href):
    """Add the entity-href to managed_entities, save the SAM, and update the entity."""
    sam = SharedAttributeManager.objects.get(pk=sam_pk)

    if entity_href not in sam.managed_entities:
        sam.managed_entities.append(entity_href)
        sam.save()
        update_entity(entity_href, sam)


def remove_entity(sam_pk, entity_href):
    """Remove the href from managed-entities and save the SAM."""
    sam = SharedAttributeManager.objects.get(pk=sam_pk)

    if entity_href in sam.managed_entities:
        sam.managed_entities.remove(entity_href)
        sam.save()


def update_entity(entity_href, sam):
    """
    Update a given entity based on the attributes being managed by a SAM.

    SAM has managed_attributes and managed_sensitive_attributes. In the case of any overlap,
    we prefer managed_sensitive_attributes.

    Args:
        entity_href(str): str-href of the Thing whose attributes we want to change
        sam(SharedAttributeManager): the SAM whose attributes we're going to apply

    Raises:
        ValidationError: if the proposed-attributes fail the entity's serializer-validation
    """

    # If there are no attributes, short-circuit to save some db-access and do nothing
    if not (sam.managed_attributes or sam.managed_sensitive_attributes):
        return

    # Find the managed-entity from its href
    from pulpcore.app.viewsets import NamedModelViewSet  # prevent circular-import-problem

    entity = NamedModelViewSet.get_resource(entity_href)

    proposed_attrs = {}
    if sam.managed_attributes:
        # Find the managed-attrs that apply to "this" entity.
        for k in sam.managed_attributes.keys():
            if hasattr(entity, k):
                proposed_attrs[k] = sam.managed_attributes[k]

    if sam.managed_sensitive_attributes:
        # Repeat for managed-sensitive-attrs, overriding any from managed-attrs
        for k in sam.managed_sensitive_attributes.keys():
            if hasattr(entity, k):
                proposed_attrs[k] = sam.managed_sensitive_attributes[k]

    # validate the proposed attrs (if there are any), and apply them
    if proposed_attrs:
        entity_viewset = util.get_viewset_for_model(entity)
        entity_serializer_class = entity_viewset().get_serializer_class()
        entity_serializer = entity_serializer_class(entity, data=proposed_attrs, partial=True)
        entity_serializer.is_valid(raise_exception=True)
        validated_attrs = entity_serializer.validated_data
        for k in validated_attrs.keys():
            setattr(entity, k, validated_attrs[k])
        entity.save()


def update_managed_entities(sam_pk):
    """Have the SAM apply all attributes to all managed entities."""
    sam = SharedAttributeManager.objects.get(pk=sam_pk)
    task = Task.current()
    accumulated_errors = {}
    with ProgressReport(
        message="Updating Managed Entities", code="sam.apply", total=len(sam.managed_entities)
    ) as total, ProgressReport(
        message="Successful Updates", code="sam.apply_success", total=len(sam.managed_entities)
    ) as succeeded, ProgressReport(
        message="Failed Updates", code="sam.apply_failures", total=len(sam.managed_entities)
    ) as failed:
        for entity in total.iter(sam.managed_entities):
            # Update entities one-at-a-time
            # Problems log at the individual-entity level
            # Do not abort at failure
            # TODO: is task a failure if any entity fails?
            try:
                update_entity(entity, sam)
                succeeded.increment()
            except ValidationError as ve:
                # Report on validation-errors. Fail Horribly on anything else.
                err_str = "Validation errors: {}".format(str(ve))
                accumulated_errors[entity] = err_str
                failed.increment()
    if accumulated_errors:
        task.error = accumulated_errors
        task.save()
