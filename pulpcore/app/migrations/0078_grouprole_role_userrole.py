# Generated by Django 3.2.7 on 2021-09-17 10:23

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django_lifecycle.mixins
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('core', '0077_move_remote_url_credentials'),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('pulp_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('pulp_created', models.DateTimeField(auto_now_add=True)),
                ('pulp_last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('name', models.CharField(db_index=True, max_length=128, unique=True)),
                ('description', models.TextField(null=True)),
                ('permissions', models.ManyToManyField(to='auth.Permission')),
                ('locked', models.BooleanField(default=False)),
            ],
            options={
                'abstract': False,
            },
            bases=(django_lifecycle.mixins.LifecycleModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('pulp_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('pulp_created', models.DateTimeField(auto_now_add=True)),
                ('pulp_last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('object_id', models.CharField(max_length=255, null=True)),
                ('content_type', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='object_users', to='core.role')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='object_roles', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['content_type', 'object_id'], name='core_userro_content_5c0477_idx')],
                'unique_together': {('user', 'role', 'content_type', 'object_id')},
            },
            bases=(django_lifecycle.mixins.LifecycleModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='GroupRole',
            fields=[
                ('pulp_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('pulp_created', models.DateTimeField(auto_now_add=True)),
                ('pulp_last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('object_id', models.CharField(max_length=255, null=True)),
                ('content_type', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='object_roles', to='auth.group')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='object_groups', to='core.role')),
            ],
            options={
                'indexes': [models.Index(fields=['content_type', 'object_id'], name='core_groupr_content_ea7d37_idx')],
                'unique_together': {('group', 'role', 'content_type', 'object_id')},
            },
            bases=(django_lifecycle.mixins.LifecycleModelMixin, models.Model),
        ),
    ]
