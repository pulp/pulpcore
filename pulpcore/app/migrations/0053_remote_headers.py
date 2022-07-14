# Generated by Django 2.2.17 on 2021-01-20 14:34

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0052_tasking_logging_cid'),
    ]

    operations = [
        migrations.AddField(
            model_name='remote',
            name='headers',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True),
        ),
    ]
