from gettext import gettext as _

from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import ModelSerializer


class ProgressReportSerializer(ModelSerializer):

    message = serializers.CharField(
        help_text=_("The message shown to the user for the progress report."), read_only=True
    )
    code = serializers.CharField(
        help_text=_("Identifies the type of progress report'."), read_only=True
    )
    state = serializers.CharField(
        help_text=_(
            "The current state of the progress report. The possible values are:"
            " 'waiting', 'skipped', 'running', 'completed', 'failed', 'canceled' and 'canceling'."
            " The default is 'waiting'."
        ),
        read_only=True,
    )
    total = serializers.IntegerField(help_text=_("The total count of items."), read_only=True)
    done = serializers.IntegerField(
        help_text=_("The count of items already processed. Defaults to 0."), read_only=True
    )
    suffix = serializers.CharField(
        help_text=_("The suffix to be shown with the progress report."),
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = models.ProgressReport
        # this serializer is meant to be nested inside Task serializer,
        # so it will not have its own endpoint, that's why
        # we need to explicitly define fields to exclude 'pulp_href' field.
        fields = ("message", "code", "state", "total", "done", "suffix")


class GroupProgressReportSerializer(ModelSerializer):

    message = serializers.CharField(
        help_text=_("The message shown to the user for the group progress report."), read_only=True
    )
    code = serializers.CharField(
        help_text=_("Identifies the type of group progress report'."), read_only=True
    )
    total = serializers.IntegerField(help_text=_("The total count of items."), read_only=True)
    done = serializers.IntegerField(
        help_text=_("The count of items already processed. Defaults to 0."), read_only=True
    )
    suffix = serializers.CharField(
        help_text=_("The suffix to be shown with the group progress report."),
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = models.GroupProgressReport
        # this serializer is meant to be nested inside TaskGroup serializer,
        # so it will not have its own endpoint, that's why
        # we need to explicitly define fields to exclude 'pulp_href' field.
        fields = ("message", "code", "total", "done", "suffix")
