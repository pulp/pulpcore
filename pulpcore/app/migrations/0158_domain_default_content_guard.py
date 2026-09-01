import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0157_distribution_base_path_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="default_content_guard",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="core.contentguard",
            ),
        ),
    ]
