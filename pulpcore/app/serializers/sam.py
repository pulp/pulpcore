from gettext import gettext as _
from logging import getLogger

from rest_framework.validators import UniqueValidator
from rest_framework.serializers import (
    CharField,
    DictField,
    JSONField,
    ListField,
    Serializer,
    ValidationError,
)

from pulpcore.app.models import SharedAttributeManager

from pulpcore.app.serializers import (
    IdentityField,
    ModelSerializer,
    ValidateFieldsMixin,
)

log = getLogger(__name__)


class ManagedResourceExistsSerializer(Serializer, ValidateFieldsMixin):
    """
    Serialize a single HREF being handed to a SAM and validate that it is an extant object.

    Fields:
        entity_href (CharField): href of an entity to be added/removed
    """

    entity_href = CharField(
        required=True,
        help_text=_("Entity to be added or removed from the SharedAttributeManager."),
    )

    def validate_entity_href(self, href):
        """
        Check that the entity_href is a valid hrefs.
        Args:
            href (str): The href supplied by the user
        Returns:
            The href after validation
        Raises:
            ValidationError: If the value provided is not an existing HREF, if must_exist=True
        """
        if not href:
            raise ValidationError("Must not be empty.")

        from pulpcore.app.viewsets import NamedModelViewSet

        try:
            NamedModelViewSet.get_resource(href)
        except Exception:
            raise ValidationError(_("Could not find entity with href {}.").format(href))

        return href


class ManagedResourceSerializer(Serializer, ValidateFieldsMixin):
    """
    A single HREF asking to be removed from a SAM.

    Fields:
        entity_href (CharField): href of an entity to be added/removed
    """

    entity_href = CharField(
        required=True,
        help_text=_("Entity-href to be removed from the SharedAttributeManager."),
    )


class SharedAttributeManagerSerializer(ModelSerializer):
    """
    Serializes SharedAttributeManagers.

    Validates managed_entities on update to make sure they exist.
    """

    pulp_href = IdentityField(view_name="shared-attribute-managers-detail")
    name = CharField(
        help_text=_("A unique name for this repository."),
        validators=[UniqueValidator(queryset=SharedAttributeManager.objects.all())],
    )
    managed_attributes = DictField(
        child=JSONField(),
        help_text=_("A JSON Object of the attributes and values being managed by this object."),
        required=False,
    )
    managed_sensitive_attributes = DictField(
        child=JSONField(),
        help_text=_(
            "A JSON Object of privacy-sensitive attributes and values being managed by this object."
        ),
        required=False,
        write_only=True,
    )
    managed_entities = ListField(
        child=CharField(),
        help_text=_("A list of HREFs of the entities being managed."),
        required=False,
    )

    def validate_managed_entities(self, value):
        """
        If we've been handed a list of HREFs, make sure we can find what they point at.

        If we can't, raise an error with the list that failed.
        """
        if not value:
            return value

        # have to import here to avoid circular-import-problem
        from pulpcore.app.viewsets import NamedModelViewSet

        failed_uris = []
        # Try all, record the ones that fail
        for href in value:
            try:
                NamedModelViewSet.get_resource(href)
            except ValidationError:
                failed_uris.append(href)

        # If anybody failed, report back the whole failed list, and fail the validation.
        if failed_uris:
            raise ValidationError(detail=_("URIs not found: {u}").format(u=failed_uris))

        return value

    # TODO: THIS IS EXAMPLE CODE ONLY!!
    def to_representation(self, sam):
        sensitive_attrs = ["password", "proxy_password"]
        for k in sensitive_attrs:
            if sam.managed_attributes and k in sam.managed_attributes:
                sam.managed_attributes[k] = "HIDDEN"
        rc = super().to_representation(sam)
        return rc

    class Meta:
        model = SharedAttributeManager
        fields = ModelSerializer.Meta.fields + (
            "name",
            "managed_attributes",
            "managed_sensitive_attributes",
            "managed_entities",
        )
