from gettext import gettext as _

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from guardian.models.models import GroupObjectPermission
from rest_framework import serializers

from pulpcore.app.serializers import IdentityField, ValidateFieldsMixin
from pulpcore.app.util import get_viewset_for_model, get_request_without_query_params


class PermissionField(serializers.CharField):
    """Permission field."""

    def to_representation(self, obj):
        permission = getattr(obj, "permission", obj)
        return f"{permission.content_type.app_label}.{permission.codename}"


class ContentObjectField(serializers.CharField):
    """Content object field"""

    def to_representation(self, obj):
        content_object = getattr(obj, "content_object", None)
        if content_object:
            viewset = get_viewset_for_model(obj.content_object)

            request = get_request_without_query_params(self.context)

            serializer = viewset.serializer_class(obj.content_object, context={"request": request})
            return serializer.data.get("pulp_href")


class PermissionSerializer(serializers.Serializer):
    """Serializer for User/Group object permission."""

    pulp_href = serializers.SerializerMethodField(read_only=True)
    id = serializers.SerializerMethodField(read_only=True)
    permission = PermissionField(source="*", read_only=True)
    obj = ContentObjectField(help_text=_("Content object."), source="*", read_only=True)

    def get_id(self, obj) -> int:
        """Get model/object permission id."""
        return obj.id

    def get_pulp_href(self, obj) -> str:
        """Get model/object permission pulp_href."""
        group_pk = self.context.get("group_pk")

        if group_pk and isinstance(obj, Permission):
            return reverse("model_permissions-detail", args=[group_pk, obj.pk])

        if group_pk and isinstance(obj, GroupObjectPermission):
            return reverse("object_permissions-detail", args=[group_pk, obj.pk])

    def to_representation(self, obj):
        representation = super().to_representation(obj)

        if not self.context.get("group_pk"):
            representation.pop("pulp_href")

        return representation


class UserGroupSerializer(serializers.ModelSerializer):
    """Serializer for Groups that belong to an User."""

    name = serializers.CharField(help_text=_("Name."), max_length=150)
    pulp_href = IdentityField(view_name="groups-detail")

    class Meta:
        model = Group
        fields = ("name", "pulp_href")


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User."""

    pulp_href = IdentityField(view_name="users-detail")
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        max_length=150,
    )
    first_name = serializers.CharField(help_text=_("First name"), max_length=150, allow_blank=True)
    last_name = serializers.CharField(help_text=_("Last name"), max_length=150, allow_blank=True)
    email = serializers.EmailField(help_text=_("Email address"), allow_blank=True)
    is_staff = serializers.BooleanField(
        help_text=_("Designates whether the user can log into this admin site."), default=False
    )
    is_active = serializers.BooleanField(
        help_text=_("Designates whether this user should be treated as active."), default=True
    )
    date_joined = serializers.DateTimeField(help_text=_("Date joined"), read_only=True)
    groups = UserGroupSerializer(read_only=True, many=True)

    class Meta:
        model = get_user_model()
        fields = (
            "pulp_href",
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "is_active",
            "date_joined",
            "groups",
        )


class GroupUserSerializer(ValidateFieldsMixin, serializers.ModelSerializer):
    """Serializer for Users that belong to a Group."""

    username = serializers.CharField(
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        max_length=150,
    )
    pulp_href = IdentityField(view_name="users-detail")

    class Meta:
        model = get_user_model()
        fields = ("username", "pulp_href")


class GroupSerializer(ValidateFieldsMixin, serializers.ModelSerializer):
    """Serializer for Group."""

    pulp_href = IdentityField(view_name="groups-detail")
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(help_text=_("Name"), max_length=150)

    class Meta:
        model = Group
        fields = ("name", "pulp_href", "id")
