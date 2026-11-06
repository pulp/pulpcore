from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0162_repository_staging_autocommit_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="repository",
            name="next_commit",
            field=models.DateTimeField(db_index=True, null=True),
        ),
    ]
