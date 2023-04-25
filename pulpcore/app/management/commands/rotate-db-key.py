from contextlib import suppress
from gettext import gettext as _

from django.apps import apps
from django.core.management import BaseCommand
from django.db import connection, transaction

from pulpcore.app.models import MasterModel
from pulpcore.app.models.fields import EncryptedTextField, EncryptedJSONField


class DryRun(Exception):
    pass


class Command(BaseCommand):
    """
    Django management command for db key rotation.
    """

    help = _(
        "Rotate the db encryption key. "
        "This command will re-encrypt all values in instances of EncryptedTextField and "
        "EncryptedJSONField with the first key in the file refereced by "
        "settings.DB_ENCRYPTION_KEY. You need to make sure that all running instances of the "
        "application already loaded this key for proper functioning. Refer to the docs for zero "
        "downtime key rotation."
        "It is safe to abort and resume or rerun this operation."
    )

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Don't modify anything."),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        for model in apps.get_models():
            if issubclass(model, MasterModel) and model._meta.master_model is None:
                # This is a master model, and we will handle all it's descendents.
                continue
            field_names = [
                field.name
                for field in model._meta.get_fields()
                if isinstance(field, (EncryptedTextField, EncryptedJSONField))
            ]
            if field_names:
                print(
                    _("Updating {fields} on {model}.").format(
                        model=model.__name__, fields=",".join(field_names)
                    )
                )
                exclude_filters = {f"{field_name}": None for field_name in field_names}
                qs = model.objects.exclude(**exclude_filters).only(*field_names)
                with suppress(DryRun), transaction.atomic():
                    batch = []
                    for item in qs.iterator():
                        batch.append(item)
                        if len(batch) >= 1024:
                            model.objects.bulk_update(batch, field_names)
                            batch = []
                    if batch:
                        model.objects.bulk_update(batch, field_names)
                        batch = []
                    if dry_run:
                        with connection.cursor() as cursor:
                            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                        raise DryRun()
