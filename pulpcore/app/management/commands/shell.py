from django.core.management.commands import shell


class Command(shell.Command):
    def get_auto_imports(self):
        # disable automatic imports. See
        # https://docs.djangoproject.com/en/5.2/howto/custom-shell/
        return None
