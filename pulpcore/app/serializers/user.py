from gettext import gettext as _

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from guardian.models.models import GroupObjectPermission
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer

from pulpcore.app.models import Group
from pulpcore.app.models.role import GroupRole, Role, UserRole
from pulpcore.app.serializers import (
    NestedIdentityField,
    IdentityField,
    ValidateFieldsMixin,
    ModelSerializer,
)
from pulpcore.app.util import get_viewset_for_model, get_request_without_query_params

User = get_user_model()


class ThisPermissionField(serializers.CharField):
    """Read only field that represents the Permission of the object.
    The object can be either a plain Permission, or GroupObjectPermission.
    """

    def to_representation(self, value):
        permission = getattr(value, "permission", value)
        return f"{permission.content_type.app_label}.{permission.codename}"


class PermissionField(serializers.RelatedField):
    """Read write Permission field."""

    queryset = Permission.objects.all()

    def to_representation(self, value):
        permission = getattr(value, "permission", value)
        return f"{permission.content_type.app_label}.{permission.codename}"

    def to_internal_value(self, data):
        try:
            app_label, codename = data.split(".", maxsplit=1)
        except Exception:
            raise serializers.ValidationError(
                _("Permission '{name}' is not in the format '<app_label>.<codename>'.").format(
                    name=data
                )
            )
        try:
            queryset = self.get_queryset()
            return queryset.get(content_type__app_label=app_label, codename=codename)
        except Permission.DoesNotExist:
            raise serializers.ValidationError(
                _("Permission '{name}' does not exist.").format(name=data)
            )


class ContentObjectField(serializers.CharField):
    """Content object field"""

    def to_representation(self, obj):
        content_object = getattr(obj, "content_object", None)
        if content_object:
            viewset = get_viewset_for_model(obj.content_object)

            request = get_request_without_query_params(self.context)

            serializer = viewset.serializer_class(obj.content_object, context={"request": request})
            return serializer.data.get("pulp_href")

    def to_internal_value(self, data):
        # ... circular import ...
        from pulpcore.app.viewsets.base import NamedModelViewSet

        if data is None:
            return {"content_object": None}
        try:
            obj = NamedModelViewSet.get_resource(data)
        except serializers.ValidationError:
            raise serializers.ValidationError(_("Invalid value: {}.").format(data))
        return {"content_object": obj}


class PermissionSerializer(serializers.Serializer):
    """Serializer for User/Group object permission."""

    pulp_href = serializers.SerializerMethodField(read_only=True)
    id = serializers.SerializerMethodField(read_only=True)
    permission = ThisPermissionField(source="*", read_only=True)
    obj = ContentObjectField(
        help_text=_("pulp_href of the object the permission is to be asserted on."),
        source="*",
        read_only=True,
    )

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
        validators=[UniqueValidator(queryset=User.objects.all())],
    )
    password = serializers.CharField(
        help_text=_("Users password. Set to ``null`` to disable password authentication."),
        write_only=True,
        allow_null=True,
        default=None,
        style={"input_type": "password"},
    )
    first_name = serializers.CharField(
        help_text=_("First name"), max_length=150, allow_blank=True, required=False
    )
    last_name = serializers.CharField(
        help_text=_("Last name"), max_length=150, allow_blank=True, required=False
    )
    email = serializers.EmailField(help_text=_("Email address"), allow_blank=True, required=False)
    is_staff = serializers.BooleanField(
        help_text=_("Designates whether the user can log into this admin site."), default=False
    )
    is_active = serializers.BooleanField(
        help_text=_("Designates whether this user should be treated as active."), default=True
    )
    date_joined = serializers.DateTimeField(help_text=_("Date joined"), read_only=True)
    groups = UserGroupSerializer(read_only=True, many=True)

    def validate(self, data):
        data = super().validate(data)
        if "password" in data:
            # `None` will automatically result in an unusable password
            if data["password"] is not None:
                validate_password(data["password"])
            data["password"] = make_password(data["password"])
        return data

    class Meta:
        model = User
        fields = (
            "pulp_href",
            "id",
            "username",
            "password",
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
        model = User
        fields = ("username", "pulp_href")


class GroupSerializer(ValidateFieldsMixin, serializers.ModelSerializer):
    """Serializer for Group."""

    pulp_href = IdentityField(view_name="groups-detail")
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(
        help_text=_("Name"),
        max_length=150,
        validators=[UniqueValidator(queryset=Group.objects.all())],
    )

    class Meta:
        model = Group
        fields = ("name", "pulp_href", "id")


class RoleSerializer(ModelSerializer):
    """Serializer for Role."""

    pulp_href = IdentityField(view_name="roles-detail")

    name = serializers.CharField(
        help_text=_("The name of this role."),
        validators=[UniqueValidator(queryset=Role.objects.all())],
    )

    description = serializers.CharField(
        help_text=_("An optional description."), required=False, allow_null=True
    )

    permissions = PermissionField(
        many=True,
        help_text=_("List of permissions defining the role."),
    )

    locked = serializers.BooleanField(
        help_text=_("True if the role is system managed."),
        read_only=True,
    )

    def create(self, validated_data):
        permissions = validated_data.pop("permissions")
        instance = super().create(validated_data)
        instance.permissions.set(permissions)
        return instance

    def update(self, instance, validated_data):
        permissions = validated_data.pop("permissions", None)
        instance = super().update(instance, validated_data)
        if permissions is not None:
            instance.permissions.set(permissions)
        return instance

    class Meta:
        model = Role
        fields = ModelSerializer.Meta.fields + (
            "name",
            "description",
            "permissions",
            "locked",
        )


class UserRoleSerializer(ModelSerializer, NestedHyperlinkedModelSerializer):
    """Serializer for UserRole."""

    pulp_href = NestedIdentityField(
        view_name="roles-detail", parent_lookup_kwargs={"user_pk": "user__pk"}
    )

    role = serializers.SlugRelatedField(
        slug_field="name",
        queryset=Role.objects.all(),
    )

    content_object = ContentObjectField(
        help_text=_("Optional pulp_href of the object the permissions are to be asserted on."),
        source="*",
        allow_null=True,
    )

    def validate(self, data):
        data = super().validate(data)
        data["user"] = User.objects.get(pk=self.context["request"].resolver_match.kwargs["user_pk"])

        natural_key_args = {
            "user_id": data["user"].pk,
            "role_id": data["role"].pk,
            "object_id": None,
            "content_type": None,
        }
        content_object = data["content_object"]
        if content_object:
            content_type = ContentType.objects.get_for_model(
                content_object, for_concrete_model=False
            )
            if not data["role"].permissions.filter(content_type__pk=content_type.id).exists():
                raise serializers.ValidationError(
                    _("The role '{}' does not carry any permission for that object.").format(
                        data["role"].name
                    )
                )
            natural_key_args["object_id"] = content_object.pk
            natural_key_args["content_type"] = content_type
        if self.Meta.model.objects.filter(**natural_key_args).exists():
            raise serializers.ValidationError(_("The role is already assigned to this user."))
        return data

    class Meta:
        model = UserRole
        fields = ModelSerializer.Meta.fields + ("role", "content_object")


class GroupRoleSerializer(ModelSerializer, NestedHyperlinkedModelSerializer):
    """Serializer for GroupRole."""

    pulp_href = NestedIdentityField(
        view_name="roles-detail", parent_lookup_kwargs={"group_pk": "group__pk"}
    )

    role = serializers.SlugRelatedField(
        slug_field="name",
        queryset=Role.objects.all(),
    )

    content_object = ContentObjectField(
        help_text=_("Optional pulp_href of the object the permissions are to be asserted on."),
        source="*",
        allow_null=True,
    )

    def validate(self, data):
        data = super().validate(data)
        data["group"] = Group.objects.get(
            pk=self.context["request"].resolver_match.kwargs["group_pk"]
        )

        natural_key_args = {
            "group_id": data["group"].pk,
            "role_id": data["role"].pk,
            "object_id": None,
            "content_type": None,
        }
        content_object = data["content_object"]
        if content_object:
            content_type = ContentType.objects.get_for_model(
                content_object, for_concrete_model=False
            )
            if not data["role"].permissions.filter(content_type__pk=content_type.id).exists():
                raise serializers.ValidationError(
                    _("The role '{}' does not carry any permission for that object.").format(
                        data["role"].name
                    )
                )
            natural_key_args["object_id"] = content_object.pk
            natural_key_args["content_type"] = content_type
        if self.Meta.model.objects.filter(**natural_key_args).exists():
            raise serializers.ValidationError(_("The role is already assigned to this group."))
        return data

    class Meta:
        model = GroupRole
        fields = ModelSerializer.Meta.fields + ("role", "content_object")


class NestedRoleSerializer(serializers.Serializer):
    """
    Serializer to add/remove object roles to/from users/groups.

    This is used in conjunction with ``pulpcore.app.viewsets.base.RolesMixin`` and requires the
    underlying object to be passed as ``content_object`` in the context.
    """

    users = serializers.ListField(
        default=[],
        child=serializers.SlugRelatedField(
            slug_field="username",
            queryset=User.objects.all(),
        ),
    )
    groups = serializers.ListField(
        default=[],
        child=serializers.SlugRelatedField(
            slug_field="name",
            queryset=Group.objects.all(),
        ),
    )

    role = serializers.SlugRelatedField(
        slug_field="name",
        queryset=Role.objects.all(),
        required=True,
    )

    def validate(self, data):
        data = super().validate(data)
        if "assign" in self.context:
            obj = self.context["content_object"]
            obj_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)

            if not data["role"].permissions.filter(content_type__pk=obj_type.id).exists():
                raise serializers.ValidationError(
                    _("The role does not contain any permission for that object.")
                )

            self.user_role_pks = []
            for user in data["users"]:
                qs = UserRole.objects.filter(
                    content_type_id=obj_type.id, object_id=obj.pk, user=user, role=data["role"]
                )
                if self.context["assign"]:
                    if qs.exists():
                        raise serializers.ValidationError(
                            _("The role is already assigned to user '{user}'.").format(
                                user=user.username
                            )
                        )
                else:
                    if not qs.exists():
                        raise serializers.ValidationError(
                            _("The role is not assigned to user '{user}'.").format(
                                user=user.username
                            )
                        )
                    self.user_role_pks.append(qs.get().pk)

            self.group_role_pks = []
            for group in data["groups"]:
                qs = GroupRole.objects.filter(
                    content_type_id=obj_type.id, object_id=obj.pk, group=group, role=data["role"]
                )
                if self.context["assign"]:
                    if qs.exists():
                        raise serializers.ValidationError(
                            _("The role is already assigned to group '{group}'.").format(
                                group=group.name
                            )
                        )
                else:
                    if not qs.exists():
                        raise serializers.ValidationError(
                            _("The role is not assigned to group '{group}'.").format(
                                group=group.name
                            )
                        )
                    self.group_role_pks.append(qs.get().pk)
        return data
