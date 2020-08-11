from gettext import gettext as _

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from rest_framework import serializers

from pulpcore.app.serializers import IdentityField
from pulpcore.app.util import get_viewset_for_model


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
            serializer = viewset.serializer_class(obj.content_object, context={"request": None})
            return serializer.data.get("pulp_href")


class ObjectPermissionSerializer(serializers.Serializer):
    """Serializer for user/group object permission."""

    permission = PermissionField(source="*", read_only=True)
    obj = ContentObjectField(help_text=_("Content object."), source="*", read_only=True)


class UserGroupSerializer(serializers.ModelSerializer):
    """Serializer for user groups."""

    name = serializers.CharField(help_text=_("Name."), max_length=150,)
    pulp_href = IdentityField(view_name="groups-detail")

    class Meta:
        model = Group
        fields = ("name", "pulp_href")


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user."""

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


class GroupUserSerializer(serializers.ModelSerializer):
    """Serializer for group users."""

    username = serializers.CharField(
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        max_length=150,
    )
    pulp_href = IdentityField(view_name="users-detail")

    class Meta:
        model = get_user_model()
        fields = ("username", "pulp_href")


class GroupSerializer(serializers.ModelSerializer):
    """Serializer for group."""

    pulp_href = IdentityField(view_name="groups-detail")
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(help_text=_("Name"), max_length=150)

    class Meta:
        model = Group
        fields = ("name", "pulp_href", "id")


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for group."""

    pulp_href = IdentityField(view_name="permissions-detail")
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(help_text=_("Name"), max_length=255)
    codename = serializers.CharField(help_text=_("Codename"), max_length=100)
    content_type_id = serializers.IntegerField(help_text=_("Content type id"))

    class Meta:
        model = Permission
        fields = ("pulp_href", "id", "name", "codename", "content_type_id")
