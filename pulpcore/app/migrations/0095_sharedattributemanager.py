# Generated by Django 3.2.15 on 2022-09-08 13:45

import django.contrib.postgres.fields
from django.db import migrations, models
import django_lifecycle.mixins
import pulpcore.app.models.fields
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0094_protect_repository_content'),
    ]

    operations = [
        migrations.CreateModel(
            name='SharedAttributeManager',
            fields=[
                ('pulp_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('pulp_created', models.DateTimeField(auto_now_add=True)),
                ('pulp_last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('name', models.TextField(db_index=True, unique=True)),
                ('managed_attributes', pulpcore.app.models.fields.EncryptedJSONField(blank=True, null=True)),
                ('managed_sensitive_attributes', pulpcore.app.models.fields.EncryptedJSONField(blank=True, null=True)),
                ('managed_entities', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None)),
            ],
            options={
                'abstract': False,
            },
            bases=(django_lifecycle.mixins.LifecycleModelMixin, models.Model),
        ),
    ]
