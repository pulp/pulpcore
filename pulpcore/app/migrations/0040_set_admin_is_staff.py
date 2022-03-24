# Generated by Django 2.2.13 on 2020-07-01 21:29

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import migrations


def allow_admin_as_staff(apps, schema_editor):
    user_model = get_user_model()
    try:
        admin_user = user_model.objects.get(username='admin')
    except user_model.DoesNotExist:
        pass
    else:
        admin_user.is_staff = True
        admin_user.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_change_download_concurrency'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(allow_admin_as_staff, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
