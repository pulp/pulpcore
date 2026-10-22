from django.contrib.postgres.operations import AddIndexConcurrently
from django.contrib.postgres.indexes import BtreeIndex, OpClass
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False  # required for CONCURRENTLY

    dependencies = [
        ("core", "0161_upstreampulp_remote_policy"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="contentartifact",
            index=BtreeIndex(
                OpClass("relative_path", name="text_pattern_ops"),
                name="core_contentartifact_relative_path_like",
            ),
        ),
    ]
