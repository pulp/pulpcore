# Generated by Django 2.2.17 on 2020-12-05 11:11

import hashlib
import json
import warnings
import subprocess
import tempfile

import gnupg

from django.db import migrations, models


def sign(service, filename):
    completed_process = subprocess.run(
        [service.script, filename], env={}, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    if completed_process.returncode != 0:
        raise RuntimeError()

    try:
        return_value = json.loads(completed_process.stdout)
    except json.JSONDecodeError:
        raise RuntimeError()

    return return_value


def print_warning(service):
    warnings.warn(
        "The public key migration for '{}' failed. The resource will not "
        "be valid. Consider creating a new signing service instead.".format(service.name),
        RuntimeWarning,
    )


def sign_temp_file(service, temp_file):
    try:
        return sign(service, temp_file.name)
    except RuntimeError:
        print_warning(service)
        raise


def update_model_fields(sign_results, service, gpg):
    try:
        with open(sign_results['key'], 'rb') as key:
            public_key = key.read()
            service.public_key = public_key

            import_result = gpg.import_keys(public_key)
            service.pubkey_fingerprint = import_result.fingerprints[0]
            service.save()
    except OSError:
        print_warning(service)


def migrate_public_key_values(apps, schema_editor):
    SigningService = apps.get_model('core', 'SigningService')
    gpg = gnupg.GPG()

    with tempfile.TemporaryDirectory() as temp_directory_name:
        with tempfile.NamedTemporaryFile(dir=temp_directory_name) as temp_file:
            temp_file.write(b'arbitrary data')
            temp_file.flush()

            for service in SigningService.objects.all():
                try:
                    sign_results = sign_temp_file(service, temp_file)
                except RuntimeError:
                    pass
                else:
                    update_model_fields(sign_results, service, gpg)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0053_remote_headers'),
    ]

    operations = [
        migrations.AddField(
            model_name='signingservice',
            name='public_key',
            field=models.TextField(default=''),
        ),
        migrations.AddField(
            model_name='signingservice',
            name='pubkey_fingerprint',
            field=models.TextField(default=''),
        ),
        migrations.RunPython(migrate_public_key_values, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='signingservice',
            name='public_key',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='signingservice',
            name='pubkey_fingerprint',
            field=models.TextField(),
        ),
    ]
