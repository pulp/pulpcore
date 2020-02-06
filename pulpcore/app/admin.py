from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from django.contrib.contenttypes.models import ContentType

from pulpcore.app.models import (
    AccessPolicy,
    Artifact,
    Content,
    ContentArtifact,
    RemoteArtifact,
    SigningService,
    AsciiArmoredDetachedSigningService,
    Repository,
    Remote,
    RepositoryContent,
    RepositoryVersion,
    RepositoryVersionContentDetails,
    Publication,
    PublishedArtifact,
    PublishedMetadata,
    PulpTemporaryFile,
    ContentGuard,
    BaseDistribution,
    ContentAppStatus,
    Upload,
    UploadChunk,
    GroupProgressReport,
    ProgressReport,
)


from pulpcore.app.models.importer import (
    Import,
    Importer,
    PulpImport,
    PulpImporter,
    PulpImporterRepository,
)


from pulpcore.app.models.exporter import (
    Export,
    Exporter,
    ExportedResource,
    PulpExport,
    PulpExporter,
)


from pulpcore.app.models.task import (
    ReservedResource,
    TaskReservedResource,
    ReservedResourceRecord,
    TaskReservedResourceRecord,
    Worker,
    Task,
    TaskGroup,
    CreatedResource,
)


from guardian.models.models import (
    GroupObjectPermission,
    UserObjectPermission,
)


class BaseModelAdmin(GuardedModelAdmin):
    pass


class PulpModelAdmin(BaseModelAdmin):
    pulp_readonly_fields = ("pulp_id", "pulp_created", "pulp_last_updated")
    pulp_fields = ("pulp_id", "pulp_created", "pulp_last_updated")

    def get_readonly_fields(self, request, obj=None):
        return self.pulp_readonly_fields + tuple(super().get_readonly_fields(request, obj))

    def get_fields(self, request, obj=None):
        return self.pulp_fields + tuple(super().get_fields(request, obj))


# ContentType is not a Pulp model, so no pulp_id etc, use BaseModelAdmin
@admin.register(ContentType)
class ContentTypeAdmin(BaseModelAdmin):
    list_display = ("id", "app_label", "model")


@admin.register(AccessPolicy)
class AccessPolicyAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "statements",
        "viewset_name",
        "permissions_assignment",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    search_fields = ("viewset_name",)


@admin.register(Artifact)
class ArtifactAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "file",
        "size",
        "md5",
        "sha1",
        "sha224",
        "sha256",
        "sha384",
        "sha512",
    )
    list_filter = ("pulp_created", "pulp_last_updated")


@admin.register(Content)
class ContentAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    raw_id_fields = ("_artifacts",)


@admin.register(ContentArtifact)
class ContentArtifactAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "artifact",
        "content",
        "relative_path",
    )
    list_filter = ("pulp_created", "pulp_last_updated")


@admin.register(RemoteArtifact)
class RemoteArtifactAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "url",
        "size",
        "md5",
        "sha1",
        "sha224",
        "sha256",
        "sha384",
        "sha512",
        "content_artifact",
        "remote",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "content_artifact",
        "remote",
    )


@admin.register(SigningService)
class SigningServiceAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "name",
        "script",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    search_fields = ("name",)


@admin.register(AsciiArmoredDetachedSigningService)
class AsciiArmoredDetachedSigningServiceAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "name",
        "script",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    search_fields = ("name",)


@admin.register(ReservedResource)
class ReservedResourceAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "resource",
        "worker",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "worker")
    raw_id_fields = ("tasks",)


@admin.register(TaskReservedResource)
class TaskReservedResourceAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "resource",
        "task",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "resource", "task")


@admin.register(ReservedResourceRecord)
class ReservedResourceRecordAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "resource",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    raw_id_fields = ("tasks",)


@admin.register(TaskReservedResourceRecord)
class TaskReservedResourceRecordAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "resource",
        "task",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    raw_id_fields = ("resource", "task")


@admin.register(Worker)
class WorkerAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "name",
        "last_heartbeat",
        "gracefully_stopped",
        "cleaned_up",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "last_heartbeat",
        "gracefully_stopped",
        "cleaned_up",
    )
    search_fields = ("name",)


@admin.register(Task)
class TaskAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "state",
        "name",
        "started_at",
        "finished_at",
        "error",
        "worker",
        "parent_task",
        "task_group",
        "_resource_job_id",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "started_at",
        "finished_at",
    )
    raw_id_fields = ("worker",)
    search_fields = ("name",)
    readonly_fields = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "state",
        "name",
        "started_at",
        "finished_at",
        "error",
        "worker",
        "parent_task",
        "task_group",
    )


@admin.register(TaskGroup)
class TaskGroupAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "description",
        "all_tasks_dispatched",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "all_tasks_dispatched",
    )


@admin.register(CreatedResource)
class CreatedResourceAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "content_type",
        "object_id",
        "task",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    raw_id_fields = ("content_type", "task")


@admin.register(Repository)
class RepositoryAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
        "description",
        "next_version",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    raw_id_fields = ("content",)
    search_fields = ("name",)


@admin.register(Remote)
class RemoteAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
        "url",
        "ca_cert",
        "client_cert",
        "client_key",
        "tls_validation",
        "username",
        "password",
        "proxy_url",
        "download_concurrency",
        "policy",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "tls_validation")
    search_fields = ("name",)


@admin.register(RepositoryContent)
class RepositoryContentAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "content",
        "repository",
        "version_added",
        "version_removed",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "content",
        "repository",
        "version_added",
        "version_removed",
    )


@admin.register(RepositoryVersion)
class RepositoryVersionAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "repository",
        "number",
        "complete",
        "base_version",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "complete")


@admin.register(RepositoryVersionContentDetails)
class RepositoryVersionContentDetailsAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "count_type",
        "content_type",
        "repository_version",
        "count",
    )


@admin.register(Publication)
class PublicationAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "complete",
        "pass_through",
        "repository_version",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "complete",
        "pass_through",
        "repository_version",
    )


@admin.register(PublishedArtifact)
class PublishedArtifactAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "relative_path",
        "content_artifact",
        "publication",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "content_artifact",
        "publication",
    )


@admin.register(PublishedMetadata)
class PublishedMetadataAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "relative_path",
        "publication",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "publication")


@admin.register(PulpTemporaryFile)
class PulpTemporaryFileAdmin(PulpModelAdmin):
    list_display = ("pulp_id", "pulp_created", "pulp_last_updated", "file")
    list_filter = ("pulp_created", "pulp_last_updated")


@admin.register(ContentGuard)
class ContentGuardAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
        "description",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    search_fields = ("name",)


@admin.register(BaseDistribution)
class BaseDistributionAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
        "base_path",
        "content_guard",
        "remote",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "content_guard",
        "remote",
    )
    search_fields = ("name",)


@admin.register(ContentAppStatus)
class ContentAppStatusAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "name",
        "last_heartbeat",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "last_heartbeat")
    search_fields = ("name",)


@admin.register(Upload)
class UploadAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "file",
        "size",
    )
    list_filter = ("pulp_created", "pulp_last_updated")


@admin.register(UploadChunk)
class UploadChunkAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "upload",
        "offset",
        "size",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "upload")


@admin.register(ProgressReport)
class ProgressReportAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "message",
        "code",
        "state",
        "total",
        "done",
        "task",
        "suffix",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "task")


@admin.register(GroupProgressReport)
class GroupProgressReportAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "message",
        "code",
        "total",
        "done",
        "task_group",
        "suffix",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "task_group")


@admin.register(UserObjectPermission)
class UserObjectPermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "permission", "content_type", "object_pk", "user")
    list_filter = ("permission", "content_type", "user")


@admin.register(GroupObjectPermission)
class GroupObjectPermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "permission", "content_type", "object_pk", "group")
    list_filter = ("permission", "content_type", "group")


@admin.register(Export)
class ExportAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "params",
        "task",
        "exporter",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "task", "exporter")


@admin.register(ExportedResource)
class ExportedResourceAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "content_type",
        "object_id",
        "export",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "content_type",
        "export",
    )


@admin.register(Exporter)
class ExporterAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    search_fields = ("name",)


@admin.register(PulpExport)
class PulpExportAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "params",
        "task",
        "exporter",
        "output_file_info",
        "toc_info",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "task", "exporter")


@admin.register(PulpExporter)
class PulpExporterAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
        "path",
        "last_export",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "last_export")
    raw_id_fields = ("repositories",)
    search_fields = ("name",)


@admin.register(Import)
class ImportAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "params",
        "task",
        "importer",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "task", "importer")


@admin.register(Importer)
class ImporterAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    search_fields = ("name",)


@admin.register(PulpImporter)
class PulpImporterAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "pulp_type",
        "name",
    )
    list_filter = ("pulp_created", "pulp_last_updated")
    search_fields = ("name",)


@admin.register(PulpImporterRepository)
class PulpImporterRepositoryAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "source_repo",
        "pulp_importer",
        "repository",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "pulp_importer",
        "repository",
    )


@admin.register(PulpImport)
class PulpImportAdmin(PulpModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "params",
        "task",
        "importer",
    )
    list_filter = ("pulp_created", "pulp_last_updated", "task", "importer")
