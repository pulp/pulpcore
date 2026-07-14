from contextlib import suppress
from gettext import gettext as _

from django.apps import apps
from django.conf import settings
from django.core.management import BaseCommand
from django.db import connections, transaction

from pulpcore.app.models import MasterModel
from pulpcore.app.models.fields import EncryptedJSONField, EncryptedTextField


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
        "settings.DB_ENCRYPTION_KEY. "
        "You need to make sure that all running instances of the application already loaded this "
        "key for proper functioning. "
        "Refer to the docs for zero downtime key rotation."
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

        # KI-22: an encrypted value can live on *any* configured alias -- a data-plane model's
        # encrypted field on a domain hosted on a satellite is just as much in need of rotation
        # as one on `default`. The original single-connection version of this command only ever
        # rotated `default`, silently leaving every satellite's copy of the old key in place.
        # Looping every alias here is deliberately unconditional (not gated behind
        # `len(settings.DATABASES) > 1`) since correctness, not overhead, is what matters for an
        # explicitly operator-invoked, infrequent maintenance command -- unlike the router/
        # queryset mixin's hot-path fast paths.
        for alias in settings.DATABASES:
            self._rotate_alias(alias, dry_run)

    def _rotate_alias(self, alias, dry_run):
        print(_("Rotating encrypted fields on database alias '{alias}'.").format(alias=alias))
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
                    _("Updating {fields} on {model} (alias '{alias}').").format(
                        model=model.__name__, fields=",".join(field_names), alias=alias
                    )
                )
                exclude_filters = {f"{field_name}": None for field_name in field_names}
                qs = model.objects.using(alias).exclude(**exclude_filters).only(*field_names)
                with suppress(DryRun), transaction.atomic(using=alias):
                    batch = []
                    for item in qs.iterator():
                        batch.append(item)
                        if len(batch) >= 1024:
                            model.objects.using(alias).bulk_update(batch, field_names)
                            batch = []
                    if batch:
                        model.objects.using(alias).bulk_update(batch, field_names)
                        batch = []
                    if dry_run:
                        with connections[alias].cursor() as cursor:
                            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                        raise DryRun()
