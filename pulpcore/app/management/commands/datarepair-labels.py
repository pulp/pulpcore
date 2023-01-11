from gettext import gettext as _

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.core.management import BaseCommand
from django.db.models.expressions import OuterRef, RawSQL


class Command(BaseCommand):
    """
    Django management command for repairing unmigrated pulp_labels.
    """

    help = _(
        "Attempts to migrate pulp_labels from a generic relation to an hstore field on their "
        "respective model."
    )

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Don't modify anything, just collect results on how many Remotes are impacted."),
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help=_("Purge all remaining Labels that could not be migrated."),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        purge = options["purge"]

        try:
            Label = apps.get_model("core", "label")
        except LookupError:
            print("Nothing to do.")
            return

        labeled_ctypes = [
            ContentType.objects.get(pk=pk)
            for pk in Label.objects.values_list("content_type", flat=True).distinct()
        ]
        for ctype in labeled_ctypes:
            model = ctype.model_class()

            if not hasattr(model, "pulp_labels"):
                print(
                    _(
                        "Warning! "
                        "Labels for content_type {app_label}.{model} could not be migrated. "
                        "Model has no labels."
                    ).format(app_label=ctype.app_label, model=ctype.model)
                )
                continue

            print(
                _("Migrate labels for content_type {app_label}.{model}.").format(
                    app_label=ctype.app_label, model=ctype.model
                )
            )
            if not dry_run:
                with transaction.atomic():
                    label_subq = (
                        Label.objects.filter(content_type=ctype, object_id=OuterRef("pulp_id"))
                        .annotate(label_data=RawSQL("hstore(array_agg(key), array_agg(value))", []))
                        .values("label_data")
                    )
                    model.objects.annotate(old_labels=label_subq).exclude(old_labels={}).update(
                        pulp_labels=label_subq
                    )
                    Label.objects.filter(content_type=ctype).delete()

        if Label.objects.count() and purge and not dry_run:
            print("Purge remaining labels.")
            Label.objects.all().delete()
