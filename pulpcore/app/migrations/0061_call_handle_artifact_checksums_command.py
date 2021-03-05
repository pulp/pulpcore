# Generated by Django 2.2.19 on 2021-03-05 18:35

from django.core.management import call_command
from django.db import migrations


def call_handle_artifact_checksums_command(apps, schema_editor):
    call_command('handle-artifact-checksums')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0060_data_migration_proxy_creds'),
    ]

    operations = [
        migrations.RunPython(
            call_handle_artifact_checksums_command,
            reverse_code=call_handle_artifact_checksums_command
        ),
    ]
