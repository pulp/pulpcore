from django.contrib import admin

from django.contrib.contenttypes.models import (
    ContentType,
)

from pulpcore.app.models import (
    # BaseModel,
    # MasterModel,

    Artifact,
    Content,
    ContentArtifact,
    RemoteArtifact,
    SigningService,
    AsciiArmoredDetachedSigningService,

    FileSystemExporter,

    Repository,
    Remote,
    RepositoryContent,
    RepositoryVersion,
    RepositoryVersionContentDetails,

    Publication,
    PublishedArtifact,
    PublishedMetadata,
    ContentGuard,
    BaseDistribution,

    ContentAppStatus,

    Upload,
    UploadChunk,

    ProgressReport,
)

from pulpcore.app.models.task import (
    ReservedResource,
    TaskReservedResource,
    ReservedResourceRecord,
    TaskReservedResourceRecord,
    Worker,
    Task,
    CreatedResource,
)


class BaseModelAdmin(admin.ModelAdmin):
    readonly_fields = ('pulp_id', 'pulp_created', 'pulp_last_updated')
    fields = ('pulp_id', 'pulp_created', 'pulp_last_updated')


@admin.register(ContentType)
class ContentTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'app_label', 'model')


@admin.register(Artifact)
class ArtifactAdmin(BaseModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'file',
        'size',
        'md5',
        'sha1',
        'sha224',
        'sha256',
        'sha384',
        'sha512',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')


@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    raw_id_fields = ('_artifacts',)


@admin.register(ContentArtifact)
class ContentArtifactAdmin(BaseModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'artifact',
        'content',
        'relative_path',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')


@admin.register(RemoteArtifact)
class RemoteArtifactAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'url',
        'size',
        'md5',
        'sha1',
        'sha224',
        'sha256',
        'sha384',
        'sha512',
        'content_artifact',
        'remote',
    )
    list_filter = (
        'pulp_created',
        'pulp_last_updated',
        'content_artifact',
        'remote',
    )


@admin.register(SigningService)
class SigningServiceAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'name',
        'script',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    search_fields = ('name',)


@admin.register(AsciiArmoredDetachedSigningService)
class AsciiArmoredDetachedSigningServiceAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'name',
        'script',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    search_fields = ('name',)


@admin.register(FileSystemExporter)
class FileSystemExporterAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
        'name',
        'path',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    search_fields = ('name',)


@admin.register(ReservedResource)
class ReservedResourceAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'resource',
        'worker',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'worker')
    raw_id_fields = ('tasks',)


@admin.register(TaskReservedResource)
class TaskReservedResourceAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'resource',
        'task',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'resource', 'task')


@admin.register(ReservedResourceRecord)
class ReservedResourceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'resource',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    raw_id_fields = ('tasks',)


@admin.register(TaskReservedResourceRecord)
class TaskReservedResourceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'resource',
        'task',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    raw_id_fields = ('resource', 'task')


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'name',
        'last_heartbeat',
        'gracefully_stopped',
        'cleaned_up',
    )
    list_filter = (
        'pulp_created',
        'pulp_last_updated',
        'last_heartbeat',
        'gracefully_stopped',
        'cleaned_up',
    )
    search_fields = ('name',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'state',
        'name',
        'started_at',
        'finished_at',
        'error',
        'worker',
    )
    list_filter = (
        'pulp_created',
        'pulp_last_updated',
        'started_at',
        'finished_at',
    )
    raw_id_fields = ('worker',)
    search_fields = ('name',)


@admin.register(CreatedResource)
class CreatedResourceAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'content_type',
        'object_id',
        'task',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    raw_id_fields = ('content_type', 'task')


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
        'name',
        'description',
        'next_version',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    raw_id_fields = ('content',)
    search_fields = ('name',)


@admin.register(Remote)
class RemoteAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
        'name',
        'url',
        'ca_cert',
        'client_cert',
        'client_key',
        'tls_validation',
        'username',
        'password',
        'proxy_url',
        'download_concurrency',
        'policy',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'tls_validation')
    search_fields = ('name',)


@admin.register(RepositoryContent)
class RepositoryContentAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'content',
        'repository',
        'version_added',
        'version_removed',
    )
    list_filter = (
        'pulp_created',
        'pulp_last_updated',
        'content',
        'repository',
        'version_added',
        'version_removed',
    )


@admin.register(RepositoryVersion)
class RepositoryVersionAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'repository',
        'number',
        'complete',
        'base_version',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'complete')


@admin.register(RepositoryVersionContentDetails)
class RepositoryVersionContentDetailsAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'count_type',
        'content_type',
        'repository_version',
        'count',
    )


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
        'complete',
        'pass_through',
        'repository_version',
    )
    list_filter = (
        'pulp_created',
        'pulp_last_updated',
        'complete',
        'pass_through',
        'repository_version',
    )


@admin.register(PublishedArtifact)
class PublishedArtifactAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'relative_path',
        'content_artifact',
        'publication',
    )
    list_filter = (
        'pulp_created',
        'pulp_last_updated',
        'content_artifact',
        'publication',
    )


@admin.register(PublishedMetadata)
class PublishedMetadataAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
        'relative_path',
        'publication',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'publication')


@admin.register(ContentGuard)
class ContentGuardAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
        'name',
        'description',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')
    search_fields = ('name',)


@admin.register(BaseDistribution)
class BaseDistributionAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'pulp_type',
        'name',
        'base_path',
        'content_guard',
        'remote',
    )
    list_filter = (
        'pulp_created',
        'pulp_last_updated',
        'content_guard',
        'remote',
    )
    search_fields = ('name',)


@admin.register(ContentAppStatus)
class ContentAppStatusAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'name',
        'last_heartbeat',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'last_heartbeat')
    search_fields = ('name',)


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'file',
        'size',
    )
    list_filter = ('pulp_created', 'pulp_last_updated')


@admin.register(UploadChunk)
class UploadChunkAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'upload',
        'offset',
        'size',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'upload')


@admin.register(ProgressReport)
class ProgressReportAdmin(admin.ModelAdmin):
    list_display = (
        'pulp_id',
        'pulp_created',
        'pulp_last_updated',
        'message',
        'code',
        'state',
        'total',
        'done',
        'task',
        'suffix',
    )
    list_filter = ('pulp_created', 'pulp_last_updated', 'task')
