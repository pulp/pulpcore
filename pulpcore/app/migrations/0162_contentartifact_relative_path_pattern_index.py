import django.contrib.postgres.indexes
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False  # required for CONCURRENTLY

    dependencies = [
        ("core", "0161_upstreampulp_remote_policy"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="contentartifact",
            index=models.Index(
                django.contrib.postgres.indexes.OpClass("relative_path", name="text_pattern_ops"),
                name="core_ca_relpath_pattern_idx",
            ),
        ),
    ]
