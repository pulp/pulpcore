# Generated by Django 2.2.20 on 2021-04-29 14:33

from django.db import migrations
import pulpcore.app.models.fields

fields = ("username", "password", "proxy_username", "proxy_password", "client_key")
new_fields = ("_encrypted_username", "_encrypted_password", "_encrypted_proxy_username", "_encrypted_proxy_password", "_encrypted_client_key")


def encrypt_remote_fields(apps, schema_editor):
    Remote = apps.get_model("core", "Remote")

    remotes_needing_update = []
    for remote in Remote.objects.all().iterator():
        if not any([getattr(remote, field) for field in fields]):
            continue

        remote._encrypted_username = remote.username
        remote._encrypted_password = remote.password
        remote._encrypted_proxy_username = remote.proxy_username
        remote._encrypted_proxy_password = remote.proxy_password
        remote._encrypted_client_key = remote.client_key
        remotes_needing_update.append(remote)

        if len(remotes_needing_update) > 100:
            Remote.objects.bulk_update(remotes_needing_update, new_fields)
            remotes_needing_update.clear()

    Remote.objects.bulk_update(remotes_needing_update, new_fields)


def unencrypt_remote_fields(apps, schema_editor):
    Remote = apps.get_model("core", "Remote")

    remotes_needing_update = []
    for remote in Remote.objects.all().iterator():
        if not any([getattr(remote, field) for field in new_fields]):
            continue
        remote.username = remote._encrypted_username
        remote.password = remote._encrypted_password
        remote.proxy_username = remote._encrypted_proxy_username
        remote.proxy_password = remote._encrypted_proxy_password
        remote.client_key = remote._encrypted_client_key
        remotes_needing_update.append(remote)

        if len(remotes_needing_update) > 100:
            Remote.objects.bulk_update(remotes_needing_update, fields)
            remotes_needing_update.clear()

    Remote.objects.bulk_update(remotes_needing_update, fields)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0072_add_method_to_filesystem_exporter"),
    ]

    operations = [
        # Add new fields to temporarily hold the encrypted values
        migrations.AddField(
            model_name="remote",
            name="_encrypted_client_key",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AddField(
            model_name="remote",
            name="_encrypted_password",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AddField(
            model_name="remote",
            name="_encrypted_proxy_password",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AddField(
            model_name="remote",
            name="_encrypted_proxy_username",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        migrations.AddField(
            model_name="remote",
            name="_encrypted_username",
            field=pulpcore.app.models.fields.EncryptedTextField(null=True),
        ),
        # Populate the new fields with encrypted values computed from the unencrypted fields
        migrations.RunPython(
            code=encrypt_remote_fields,
            reverse_code=unencrypt_remote_fields,
            elidable=True,
        ),
        # Remove the unencrypted columns
        migrations.RemoveField(
            model_name="remote",
            name="client_key",
        ),
        migrations.RemoveField(
            model_name="remote",
            name="password",
        ),
        migrations.RemoveField(
            model_name="remote",
            name="proxy_password",
        ),
        migrations.RemoveField(
            model_name="remote",
            name="proxy_username",
        ),
        migrations.RemoveField(
            model_name="remote",
            name="username",
        ),
        # Replace the formerly-unencrypted columns with the new encrypted ones
        migrations.RenameField(
            model_name="remote",
            old_name="_encrypted_client_key",
            new_name="client_key",
        ),
        migrations.RenameField(
            model_name="remote",
            old_name="_encrypted_password",
            new_name="password",
        ),
        migrations.RenameField(
            model_name="remote",
            old_name="_encrypted_proxy_password",
            new_name="proxy_password",
        ),
        migrations.RenameField(
            model_name="remote",
            old_name="_encrypted_proxy_username",
            new_name="proxy_username",
        ),
        migrations.RenameField(
            model_name="remote",
            old_name="_encrypted_username",
            new_name="username",
        ),
    ]
