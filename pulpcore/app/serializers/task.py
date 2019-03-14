from gettext import gettext as _

from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import IdentityField, RelatedField, ModelSerializer, \
    ProgressReportSerializer
from pulpcore.app.util import get_viewset_for_model


class CreatedResourceSerializer(RelatedField):

    def to_representation(self, data):
        # If the content object was deleted
        if data.content_object is None:
            return None
        try:
            if not data.content_object.complete:
                return None
        except AttributeError:
            pass
        request = self.context['request']
        viewset = get_viewset_for_model(data.content_object)
        serializer = viewset.serializer_class(data.content_object, context={'request': request})
        return serializer.data.get('_href')

    class Meta:
        model = models.CreatedResource
        fields = []


class TaskSerializer(ModelSerializer):
    _href = IdentityField(view_name='tasks-detail')
    state = serializers.CharField(
        help_text=_("The current state of the task. The possible values include:"
                    " 'waiting', 'skipped', 'running', 'completed', 'failed' and 'canceled'."),
        read_only=True
    )
    name = serializers.CharField(
        help_text=_("The name of task.")
    )
    started_at = serializers.DateTimeField(
        help_text=_("Timestamp of the when this task started execution."),
        read_only=True
    )
    finished_at = serializers.DateTimeField(
        help_text=_("Timestamp of the when this task stopped execution."),
        read_only=True
    )
    non_fatal_errors = serializers.JSONField(
        help_text=_("A JSON Object of non-fatal errors encountered during the execution of this "
                    "task."),
        read_only=True
    )
    error = serializers.JSONField(
        help_text=_("A JSON Object of a fatal error encountered during the execution of this "
                    "task."),
        read_only=True
    )
    worker = RelatedField(
        help_text=_("The worker associated with this task."
                    " This field is empty if a worker is not yet assigned."),
        read_only=True,
        view_name='workers-detail'
    )
    parent = RelatedField(
        help_text=_("The parent task that spawned this task."),
        read_only=True,
        view_name='tasks-detail'
    )
    spawned_tasks = RelatedField(
        help_text=_("Any tasks spawned by this task."),
        many=True,
        read_only=True,
        view_name='tasks-detail'
    )
    progress_reports = ProgressReportSerializer(
        many=True,
        read_only=True
    )
    created_resources = CreatedResourceSerializer(
        help_text=_('Resources created by this task.'),
        many=True,
        read_only=True,
        view_name='None'  # This is a polymorphic field. The serializer does not need a view name.
    )

    class Meta:
        model = models.Task
        fields = ModelSerializer.Meta.fields + ('state', 'name', 'started_at',
                                                'finished_at', 'non_fatal_errors', 'error',
                                                'worker', 'parent', 'spawned_tasks',
                                                'progress_reports', 'created_resources')


class MinimalTaskSerializer(TaskSerializer):

    class Meta:
        model = models.Task
        fields = ModelSerializer.Meta.fields + ('name', 'state', 'started_at', 'finished_at',
                                                'worker', 'parent')


class WorkerSerializer(ModelSerializer):
    _href = IdentityField(view_name='workers-detail')

    name = serializers.CharField(
        help_text=_('The name of the worker.'),
        read_only=True
    )
    last_heartbeat = serializers.DateTimeField(
        help_text=_('Timestamp of the last time the worker talked to the service.'),
        read_only=True
    )
    online = serializers.BooleanField(
        help_text=_('True if the worker is considered online, otherwise False'),
        read_only=True
    )
    missing = serializers.BooleanField(
        help_text=_('True if the worker is considerd missing, otherwise False'),
        read_only=True
    )
    # disable "created" because we don't care about it
    created = None

    class Meta:
        model = models.Worker
        _base_fields = tuple(set(ModelSerializer.Meta.fields) - set(['created']))
        fields = _base_fields + ('name', 'last_heartbeat', 'online', 'missing')
