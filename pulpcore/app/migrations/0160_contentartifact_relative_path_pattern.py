from django.contrib.postgres.indexes import OpClass
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("core", "0159_alter_contentartifact_relative_path_and_more"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="contentartifact",
            index=models.Index(
                OpClass("relative_path", name="text_pattern_ops"),
                name="ca_relpath_pattern_idx",
            ),
        ),
    ]
