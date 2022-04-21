from getpass import getpass
from gettext import gettext as _

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    """
    Django management command for resetting the password of the 'admin' user in Pulp.
    """

    help = 'Resets "admin" user\'s password.'

    def add_arguments(self, parser):
        exclusive = parser.add_mutually_exclusive_group()
        exclusive.add_argument(
            "--random",
            action="store_true",
            dest="random",
            default=False,
            help=_("Generate random password for 'admin' user."),
        )
        exclusive.add_argument(
            "-p",
            "--password",
            dest="password",
            default=None,
            help=_("INSECURE: Use the given password for 'admin' user."),
        )

    def handle(self, *args, **options):
        user = User.objects.get_or_create(username="admin", is_superuser=True, is_staff=True)[0]
        if options["random"]:
            password = User.objects.make_random_password(length=20)
            user.set_password(password)
            user.save()
            self.stdout.write(_('Successfully set "admin" user\'s password to "%s".') % password)
        else:
            if options["password"]:
                password = options["password"]
            else:
                # this bit duplicates behavior in the builtin "changepassword" command, so
                # at this point we can probably just call out to that command, leaving this one
                # focused on generating random passwords or setting passwords in automation
                password = getpass(_('Please enter new password for user "admin": '))
                password2 = getpass(_('Please enter new password for user "admin" again: '))
                if password != password2:
                    raise CommandError(_("The passwords did not match."))

            if not password:
                raise CommandError(_("The password must be at least 1 character long."))

            user.set_password(password)
            user.save()
            self.stdout.write(_('Successfully set password for "admin" user.'))
