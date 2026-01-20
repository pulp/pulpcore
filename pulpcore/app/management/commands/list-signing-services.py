from django.apps import apps
from django.core.management import BaseCommand


class Command(BaseCommand):
    """
    Django management command for listing signing services.
    """

    help = "List all SigningServices."

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        SigningService = apps.get_model("core", "SigningService")
        results = list(SigningService.objects.all().values_list("name", flat=True))
        self.stdout.write(results)
