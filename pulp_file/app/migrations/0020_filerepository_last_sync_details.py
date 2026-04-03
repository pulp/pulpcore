from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("file", "0019_add_filegitremote"),
    ]

    operations = [
        migrations.AddField(
            model_name="filerepository",
            name="last_sync_details",
            field=models.JSONField(default=dict),
        ),
    ]
