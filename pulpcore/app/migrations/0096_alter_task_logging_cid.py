# Generated by Django 3.2.15 on 2022-10-18 09:51

from django.db import migrations, models
from django_guid.utils import generate_guid


def migrate_empty_string_logging_cid(apps, schema_editor):

    Task = apps.get_model("core", "Task")

    for task in Task.objects.filter(logging_cid=""):
        task.logging_cid = generate_guid()
        task.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0095_artifactdistribution'),
    ]

    operations = [
        migrations.RunPython(
            migrate_empty_string_logging_cid, reverse_code=migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name='task',
            name='logging_cid',
            field=models.TextField(db_index=True),
        ),
    ]
