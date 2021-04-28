# Generated by Django 2.2.20 on 2021-04-29 14:33

from django.db import connection, migrations
from django.db.models import Q

import pulpcore.app.models.fields

fields = ("username", "password", "proxy_username", "proxy_password", "client_key")


def encrypt_remote_fields(apps, schema_editor):
    offset = 0
    chunk_size = 100
    Remote = apps.get_model("core", "Remote")

    with connection.cursor() as cursor:
        while True:
            cursor.execute(
                f"SELECT pulp_id, {(',').join(fields)} FROM "
                f"core_remote LIMIT {chunk_size} OFFSET {offset}"
            )
            records = cursor.fetchall()
            offset += chunk_size

            if len(records) == 0:
                break

            for record in records:
                update = {
                    field: record[i] for i, field in enumerate(fields, 1) if record[i] is not None
                }
                if not update:
                    continue

                Remote.objects.filter(pk=record[0]).update(**update)


def unencrypt_remote_fields(apps, schema_editor):
    Remote = apps.get_model("core", "Remote")

    q = Q()
    for field in fields:
        q &= Q(**{field: None}) | Q(**{field: ""})

    for remote in Remote.objects.exclude(q):
        update = [
            f"{field} = '{getattr(remote, field)}'"
            for field in fields
            if getattr(remote, field) is not None
        ]
        query = (
            f"UPDATE core_remote cr SET {(', ').join(update)} WHERE pulp_id = '{remote.pulp_id}'"
        )

        with connection.cursor() as cursor:
            cursor.execute(query)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0072_add_method_to_filesystem_exporter"),
    ]

    operations = [
        migrations.AlterField(
            model_name="remote",
            name="client_key",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AlterField(
            model_name="remote",
            name="password",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AlterField(
            model_name="remote",
            name="proxy_password",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AlterField(
            model_name="remote",
            name="proxy_username",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AlterField(
            model_name="remote",
            name="username",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.RunPython(
            code=encrypt_remote_fields,
            reverse_code=unencrypt_remote_fields,
        ),
    ]
