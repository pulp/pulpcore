from datetime import datetime, timedelta, timezone
from gettext import gettext as _

from rest_framework import serializers

from pulpcore.app.serializers import ValidateFieldsMixin  # noqa
from pulpcore.constants import TASK_FINAL_STATES


class PurgeSerializer(serializers.Serializer, ValidateFieldsMixin):
    finished_before = serializers.DateTimeField(
        help_text=_(
            "Purge tasks completed earlier than this timestamp. Format '%Y-%m-%d[T%H:%M:%S]'"
        ),
        default=(datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"),
    )
    states = serializers.MultipleChoiceField(
        choices=TASK_FINAL_STATES,
        default=["completed"],
        help_text=_("List of task-states to be purged. Only 'final' states are allowed."),
    )
