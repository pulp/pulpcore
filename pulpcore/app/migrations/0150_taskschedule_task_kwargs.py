# Generated manually

from django.db import migrations

import pulpcore.app.models.fields


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0149_distributedpublication"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskschedule",
            name="task_args",
            field=pulpcore.app.models.fields.EncryptedJSONField(default=list),
        ),
        migrations.AddField(
            model_name="taskschedule",
            name="task_kwargs",
            field=pulpcore.app.models.fields.EncryptedJSONField(default=dict),
        ),
    ]
