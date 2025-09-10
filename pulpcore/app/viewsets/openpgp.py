from pulpcore.app import models
from pulpcore.app.serializers.openpgp import (
    OpenPGPDistributionSerializer,
    OpenPGPKeyringSerializer,
    OpenPGPPublicKeySerializer,
    OpenPGPPublicSubkeySerializer,
    OpenPGPSignatureSerializer,
    OpenPGPUserAttributeSerializer,
    OpenPGPUserIDSerializer,
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS, RolesMixin
from pulpcore.app.viewsets.content import ContentFilter, ReadOnlyContentViewSet
from pulpcore.app.viewsets.repository import RepositoryViewSet
from pulpcore.app.viewsets.publication import DistributionFilter, DistributionViewSet
from pulpcore.plugin.actions import ModifyRepositoryActionMixin
from pulpcore.plugin.viewsets import NoArtifactContentUploadViewSet


class OpenPGPSignatureFilter(ContentFilter):
    # Wishlist: filter by expired

    class Meta:
        model = models.OpenPGPSignature
        fields = ["issuer"]


class OpenPGPUserIDFilter(ContentFilter):
    class Meta:
        model = models.OpenPGPUserID
        fields = {"user_id": NAME_FILTER_OPTIONS}


class OpenPGPUserAttributeFilter(ContentFilter):
    class Meta:
        model = models.OpenPGPUserAttribute
        fields = ["sha256"]


class OpenPGPPublicSubkeyFilter(ContentFilter):
    class Meta:
        model = models.OpenPGPPublicSubkey
        fields = ["fingerprint"]


class OpenPGPPublicKeyFilter(ContentFilter):
    # Wishlist: filter by user id

    class Meta:
        model = models.OpenPGPPublicKey
        fields = ["fingerprint"]


class OpenPGPDistributionFilter(DistributionFilter):
    class Meta:
        model = models.OpenPGPDistribution
        fields = ["repository_version"]


class OpenPGPSignatureViewSet(ReadOnlyContentViewSet):
    endpoint_name = "openpgp_signature"
    queryset = models.OpenPGPSignature.objects.all()
    serializer_class = OpenPGPSignatureSerializer
    filterset_class = OpenPGPSignatureFilter


class OpenPGPUserIDViewSet(ReadOnlyContentViewSet):
    endpoint_name = "openpgp_userid"
    queryset = models.OpenPGPUserID.objects.all()
    serializer_class = OpenPGPUserIDSerializer
    filterset_class = OpenPGPUserIDFilter


class OpenPGPUserAttributeViewSet(ReadOnlyContentViewSet):
    endpoint_name = "openpgp_userattribute"
    queryset = models.OpenPGPUserAttribute.objects.all()
    serializer_class = OpenPGPUserAttributeSerializer
    filterset_class = OpenPGPUserAttributeFilter


class OpenPGPPublicSubkeyViewSet(ReadOnlyContentViewSet):
    endpoint_name = "openpgp_publicsubkey"
    queryset = models.OpenPGPPublicSubkey.objects.all()
    serializer_class = OpenPGPPublicSubkeySerializer
    filterset_class = OpenPGPPublicSubkeyFilter


class OpenPGPPublicKeyViewSet(NoArtifactContentUploadViewSet):
    endpoint_name = "openpgp_publickey"
    queryset = models.OpenPGPPublicKey.objects.prefetch_related(
        "user_ids__openpgp_signatures",
        "user_attributes__openpgp_signatures",
        "public_subkeys__openpgp_signatures",
    )
    serializer_class = OpenPGPPublicKeySerializer
    filterset_class = OpenPGPPublicKeyFilter


class OpenPGPKeyringViewSet(RepositoryViewSet, ModifyRepositoryActionMixin, RolesMixin):
    endpoint_name = "openpgp_keyring"
    queryset = models.OpenPGPKeyring.objects.all()
    serializer_class = OpenPGPKeyringSerializer
    queryset_filtering_required_permission = "core.view_openpgpkeyring"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_perms:core.add_openpgpkeyring",
                ],
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.view_openpgpkeyring",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:core.delete_openpgpkeyring",
                ],
            },
            {
                "action": ["update", "partial_update", "set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:core.change_openpgpkeyring",
                ],
            },
            {
                "action": ["modify"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:core.modify_openpgpkeyring",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_domain_or_obj_perms:core.manage_roles_openpgpkeyring"],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "core.openpgpkeyring_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "core.openpgpkeyring_creator": {
            "description": "Create new OpenPGP keyrings.",
            "permissions": ["core.add_openpgpkeyring"],
        },
        "core.openpgpkeyring_owner": {
            "description": (
                "Full control over OpenPGP keyrings including viewing, updating, deleting, "
                "modifying content, role management, and repair operations."
            ),
            "permissions": [
                "core.view_openpgpkeyring",
                "core.change_openpgpkeyring",
                "core.delete_openpgpkeyring",
                "core.modify_openpgpkeyring",
                "core.manage_roles_openpgpkeyring",
                "core.repair_openpgpkeyring",
            ],
        },
        "core.openpgpkeyring_viewer": {
            "description": "View OpenPGP keyring details and contents.",
            "permissions": ["core.view_openpgpkeyring"],
        },
    }


class OpenPGPDistributionViewSet(DistributionViewSet):
    endpoint_name = "openpgp"
    queryset = models.OpenPGPDistribution.objects.all()
    serializer_class = OpenPGPDistributionSerializer
    filterset_class = OpenPGPDistributionFilter

    # DEFAULT_ACCESS_POLICY
