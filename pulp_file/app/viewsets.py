import os

from django_filters import CharFilter
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404

from pulpcore.plugin.actions import ModifyRepositoryActionMixin
from pulpcore.plugin.models import (
    AlternateContentSource,
    AlternateContentSourcePath,
    TaskGroup,
)
from pulpcore.plugin.serializers import (
    AsyncOperationResponseSerializer,
    RepositorySyncURLSerializer,
    TaskGroupOperationResponseSerializer,
)
from pulpcore.plugin.tasking import dispatch
from pulpcore.plugin.viewsets import (
    AlternateContentSourceViewSet,
    ContentFilter,
    DistributionViewSet,
    OperationPostponedResponse,
    PublicationViewSet,
    RemoteViewSet,
    RepositoryViewSet,
    RepositoryVersionViewSet,
    RolesMixin,
    SingleArtifactContentUploadViewSet,
    TaskGroupOperationResponse,
)

from . import tasks
from .models import (
    FileAlternateContentSource,
    FileContent,
    FileDistribution,
    FileRemote,
    FileRepository,
    FilePublication,
)
from .serializers import (
    FileAlternateContentSourceSerializer,
    FileContentSerializer,
    FileDistributionSerializer,
    FileRemoteSerializer,
    FileRepositorySerializer,
    FilePublicationSerializer,
)


class FileContentFilter(ContentFilter):
    """
    FilterSet for FileContent.
    """

    sha256 = CharFilter(field_name="digest")

    class Meta:
        model = FileContent
        fields = ["relative_path", "sha256"]


class FileContentViewSet(SingleArtifactContentUploadViewSet):
    """
    <!-- User-facing documentation, rendered as html-->
    FileContent represents a single file and its metadata, which can be added and removed from
    repositories.
    """

    endpoint_name = "files"
    queryset = FileContent.objects.prefetch_related("_artifacts")
    serializer_class = FileContentSerializer
    filterset_class = FileContentFilter

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "retrieve"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_required_repo_perms_on_upload:file.modify_filerepository",
                    "has_required_repo_perms_on_upload:file.view_filerepository",
                    "has_upload_param_model_or_domain_or_obj_perms:core.change_upload",
                ],
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }


class FileRepositoryViewSet(RepositoryViewSet, ModifyRepositoryActionMixin, RolesMixin):
    """
    <!-- User-facing documentation, rendered as html-->
    FileRepository represents a single file repository, to which content can be synced, added,
    or removed.
    """

    endpoint_name = "file"
    queryset = FileRepository.objects.exclude(user_hidden=True)
    serializer_class = FileRepositorySerializer
    queryset_filtering_required_permission = "file.view_filerepository"

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
                    "has_model_or_domain_perms:file.add_filerepository",
                    "has_remote_param_model_or_domain_or_obj_perms:file.view_fileremote",
                ],
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:file.view_filerepository",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.delete_filerepository",
                    "has_model_or_domain_or_obj_perms:file.view_filerepository",
                ],
            },
            {
                "action": ["update", "partial_update", "set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.change_filerepository",
                    "has_model_or_domain_or_obj_perms:file.view_filerepository",
                    "has_remote_param_model_or_domain_or_obj_perms:file.view_fileremote",
                ],
            },
            {
                "action": ["sync"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.sync_filerepository",
                    "has_remote_param_model_or_domain_or_obj_perms:file.view_fileremote",
                    "has_model_or_domain_or_obj_perms:file.view_filerepository",
                ],
            },
            {
                "action": ["modify"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.modify_filerepository",
                    "has_model_or_domain_or_obj_perms:file.view_filerepository",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_domain_or_obj_perms:file.manage_roles_filerepository"],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "file.filerepository_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "file.filerepository_creator": ["file.add_filerepository"],
        "file.filerepository_owner": [
            "file.view_filerepository",
            "file.change_filerepository",
            "file.delete_filerepository",
            "file.modify_filerepository",
            "file.sync_filerepository",
            "file.manage_roles_filerepository",
            "file.repair_filerepository",
        ],
        "file.filerepository_viewer": ["file.view_filerepository"],
    }

    @extend_schema(
        description="Trigger an asynchronous task to sync file content.",
        summary="Sync from a remote",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=RepositorySyncURLSerializer)
    def sync(self, request, pk):
        """
        Synchronizes a repository.

        The ``repository`` field has to be provided.
        """
        serializer = RepositorySyncURLSerializer(
            data=request.data, context={"request": request, "repository_pk": pk}
        )
        serializer.is_valid(raise_exception=True)

        repository = self.get_object()
        remote = serializer.validated_data.get("remote", repository.remote)

        mirror = serializer.validated_data.get("mirror", False)
        result = dispatch(
            tasks.synchronize,
            shared_resources=[remote],
            exclusive_resources=[repository],
            kwargs={
                "remote_pk": str(remote.pk),
                "repository_pk": str(repository.pk),
                "mirror": mirror,
            },
        )
        return OperationPostponedResponse(result, request)


class FileRepositoryVersionViewSet(RepositoryVersionViewSet):
    """
    <!-- User-facing documentation, rendered as html-->
    FileRepositoryVersion represents a single file repository version.
    """

    parent_viewset = FileRepositoryViewSet

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_repository_model_or_domain_or_obj_perms:file.view_filerepository",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_repository_model_or_domain_or_obj_perms:file.delete_filerepository",
                    "has_repository_model_or_domain_or_obj_perms:file.view_filerepository",
                ],
            },
            {
                "action": ["repair"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_repository_model_or_domain_or_obj_perms:file.repair_filerepository",
                    "has_repository_model_or_domain_or_obj_perms:file.view_filerepository",
                ],
            },
        ],
    }


class FileRemoteViewSet(RemoteViewSet, RolesMixin):
    """
    <!-- User-facing documentation, rendered as html-->
    FileRemote represents an external source of <a href="#operation/content_file_files_list">File
    Content</a>.  The target url of a FileRemote must contain a file manifest, which contains the
    metadata for all files at the source.
    """

    endpoint_name = "file"
    queryset = FileRemote.objects.all()
    serializer_class = FileRemoteSerializer
    queryset_filtering_required_permission = "file.view_fileremote"

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
                "condition": "has_model_or_domain_perms:file.add_fileremote",
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:file.view_fileremote",
            },
            {
                "action": ["update", "partial_update", "set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.change_fileremote",
                    "has_model_or_domain_or_obj_perms:file.view_fileremote",
                ],
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.delete_fileremote",
                    "has_model_or_domain_or_obj_perms:file.view_fileremote",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_domain_or_obj_perms:file.manage_roles_fileremote"],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "file.fileremote_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "file.fileremote_creator": ["file.add_fileremote"],
        "file.fileremote_owner": [
            "file.view_fileremote",
            "file.change_fileremote",
            "file.delete_fileremote",
            "file.manage_roles_fileremote",
        ],
        "file.fileremote_viewer": ["file.view_fileremote"],
    }


class FilePublicationViewSet(PublicationViewSet, RolesMixin):
    """
    <!-- User-facing documentation, rendered as html-->
    A FilePublication contains metadata about all the <a
    href="#operation/content_file_files_list">File Content</a> in a particular <a
    href=#tag/repositories:-file-versions">File Repository Version.</a>
    Once a FilePublication has been created, it can be hosted using the
    <a href="#operation/distributions_file_file_list">File Distribution API.</a>
    """

    endpoint_name = "file"
    queryset = FilePublication.objects.exclude(complete=False)
    serializer_class = FilePublicationSerializer
    queryset_filtering_required_permission = "file.view_filepublication"

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
                    "has_model_or_domain_perms:file.add_filepublication",
                    "has_repo_or_repo_ver_param_model_or_domain_or_obj_perms:"
                    "file.view_filerepository",
                ],
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:file.view_filepublication",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.delete_filepublication",
                    "has_model_or_domain_or_obj_perms:file.view_filepublication",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_domain_or_obj_perms:file.manage_roles_filepublication"],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "file.filepublication_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "file.filepublication_creator": ["file.add_filepublication"],
        "file.filepublication_owner": [
            "file.view_filepublication",
            "file.delete_filepublication",
            "file.manage_roles_filepublication",
        ],
        "file.filepublication_viewer": ["file.view_filepublication"],
    }

    @extend_schema(
        description="Trigger an asynchronous task to publish file content.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request):
        """
        Publishes a repository.

        Either the ``repository`` or the ``repository_version`` fields can
        be provided but not both at the same time.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        repository_version = serializer.validated_data.get("repository_version")
        manifest = serializer.validated_data.get("manifest")

        result = dispatch(
            tasks.publish,
            shared_resources=[repository_version.repository],
            kwargs={"repository_version_pk": str(repository_version.pk), "manifest": manifest},
        )
        return OperationPostponedResponse(result, request)


class FileDistributionViewSet(DistributionViewSet, RolesMixin):
    """
    <!-- User-facing documentation, rendered as html-->
    FileDistributions host <a href="#operation/publications_file_file_list">File
    Publications</a> which makes the metadata and the referenced <a
    href="#operation/content_file_files_list">File Content</a> available to HTTP
    clients. Additionally, a FileDistribution with an associated FilePublication can be the target
    url of a <a href="#operation/remotes_file_file_list">File Remote</a> , allowing
    another instance of Pulp to sync the content.
    """

    endpoint_name = "file"
    queryset = FileDistribution.objects.all()
    serializer_class = FileDistributionSerializer
    queryset_filtering_required_permission = "file.view_filedistribution"

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
                    "has_model_or_domain_perms:file.add_filedistribution",
                    "has_repo_or_repo_ver_param_model_or_domain_or_obj_perms:"
                    "file.view_filerepository",
                    "has_publication_param_model_or_domain_or_obj_perms:file.view_filepublication",
                ],
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:file.view_filedistribution",
            },
            {
                "action": ["update", "partial_update", "set_label", "unset_label"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.change_filedistribution",
                    "has_model_or_domain_or_obj_perms:file.view_filedistribution",
                    "has_repo_or_repo_ver_param_model_or_domain_or_obj_perms:"
                    "file.view_filerepository",
                    "has_publication_param_model_or_domain_or_obj_perms:file.view_filepublication",
                ],
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.delete_filedistribution",
                    "has_model_or_domain_or_obj_perms:file.view_filedistribution",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.manage_roles_filedistribution"
                ],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "file.filedistribution_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "file.filedistribution_creator": ["file.add_filedistribution"],
        "file.filedistribution_owner": [
            "file.view_filedistribution",
            "file.change_filedistribution",
            "file.delete_filedistribution",
            "file.manage_roles_filedistribution",
        ],
        "file.filedistribution_viewer": ["file.view_filedistribution"],
    }


class FileAlternateContentSourceViewSet(AlternateContentSourceViewSet, RolesMixin):
    """
    Alternate Content Source ViewSet for File

    ACS support is provided as a tech preview in pulp_file.
    """

    endpoint_name = "file"
    queryset = FileAlternateContentSource.objects.all()
    serializer_class = FileAlternateContentSourceSerializer
    queryset_filtering_required_permission = "file.view_filealternatecontentsource"

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
                    "has_model_or_domain_perms:file.add_filealternatecontentsource",
                    "has_remote_param_model_or_domain_or_obj_perms:file.view_fileremote",
                ],
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:"
                "file.view_filealternatecontentsource",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.change_filealternatecontentsource",
                    "has_model_or_domain_or_obj_perms:file.view_filealternatecontentsource",
                    "has_remote_param_model_or_domain_or_obj_perms:file.view_fileremote",
                ],
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.delete_filealternatecontentsource",
                    "has_model_or_domain_or_obj_perms:file.view_filealternatecontentsource",
                ],
            },
            {
                "action": ["refresh"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.refresh_filealternatecontentsource",
                    "has_model_or_domain_or_obj_perms:file.view_filealternatecontentsource",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:file.manage_roles_filealternatecontentsource"
                ],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "file.filealternatecontentsource_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "file.filealternatecontentsource_creator": ["file.add_filealternatecontentsource"],
        "file.filealternatecontentsource_owner": [
            "file.view_filealternatecontentsource",
            "file.change_filealternatecontentsource",
            "file.delete_filealternatecontentsource",
            "file.refresh_filealternatecontentsource",
            "file.manage_roles_filealternatecontentsource",
        ],
        "file.filealternatecontentsource_viewer": ["file.view_filealternatecontentsource"],
    }

    @extend_schema(
        description="Trigger an asynchronous task to create Alternate Content Source content.",
        summary="Refresh metadata",
        request=None,
        responses={202: TaskGroupOperationResponseSerializer},
    )
    @action(methods=["post"], detail=True)
    def refresh(self, request, pk):
        """
        Refresh ACS metadata.
        """
        acs = get_object_or_404(AlternateContentSource, pk=pk)
        acs_paths = AlternateContentSourcePath.objects.filter(alternate_content_source=pk)
        task_group = TaskGroup.objects.create(
            description=f"Refreshing {acs_paths.count()} alternate content source paths."
        )

        for acs_path in acs_paths:
            # Create or get repository for the path
            repo_data = {
                "name": f"{acs.name}--{acs_path.pk}--repository",
                "retain_repo_versions": 1,
                "user_hidden": True,
            }
            repo, created = FileRepository.objects.get_or_create(**repo_data)
            if created:
                acs_path.repository = repo
                acs_path.save()
            acs_url = (
                os.path.join(acs.remote.url, acs_path.path) if acs_path.path else acs.remote.url
            )

            # Dispatching ACS path to own task and assign it to common TaskGroup
            dispatch(
                tasks.synchronize,
                shared_resources=[acs.remote, acs],
                task_group=task_group,
                kwargs={
                    "remote_pk": str(acs.remote.pk),
                    "repository_pk": str(acs_path.repository.pk),
                    "mirror": False,
                    "url": acs_url,
                },
            )

        # Update TaskGroup that all child task are dispatched
        task_group.finish()
        return TaskGroupOperationResponse(task_group, request)
