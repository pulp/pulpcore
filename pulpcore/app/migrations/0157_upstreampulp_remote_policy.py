from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0156_alter_contentartifact_relative_path_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="upstreampulp",
            name="remote_policy",
            field=models.TextField(
                choices=[
                    ("immediate", "When syncing, download all metadata and content now."),
                    (
                        "on_demand",
                        "When syncing, download metadata, but do not download content now. "
                        "Instead, download content as clients request it, and save it in Pulp "
                        "to be served for future client requests.",
                    ),
                    (
                        "streamed",
                        "When syncing, download metadata, but do not download content now. "
                        "Instead,download content as clients request it, but never save it in "
                        "Pulp. This causes future requests for that same content to have to be "
                        "downloaded again.",
                    ),
                ],
                null=True,
            ),
        ),
    ]
