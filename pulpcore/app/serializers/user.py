from gettext import gettext as _

from guardian.models.models import UserObjectPermission
from django.contrib.auth.models import User, Permission
from rest_framework import serializers

from pulpcore.app.util import get_viewset_for_model


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for user."""

    name = serializers.CharField(help_text=_("Name"), max_length=255)
    codename = serializers.CharField(help_text=_("Codename"), max_length=100)

    class Meta:
        model = Permission
        fields = ("name", "codename")


class ContentObjectField(serializers.CharField):
    """Content object field"""

    def to_representation(self, obj):
        viewset = get_viewset_for_model(obj.content_object)
        serializer = viewset.serializer_class(obj.content_object, context={"request": None})
        return serializer.data.get("pulp_href")


class UserObjectPermissionSerializer(serializers.ModelSerializer):
    """Serializer for user object permission."""

    permission = PermissionSerializer()
    obj = ContentObjectField(help_text=_("Content object."), source="*", read_only=True,)

    class Meta:
        model = UserObjectPermission
        fields = ("permission", "obj")


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user."""

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

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "is_staff",
            "is_active",
            "date_joined",
        )
