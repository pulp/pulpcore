# Generated by Django 4.2.15 on 2024-10-11 08:29

from django.db import migrations, models
import django.db.models.deletion
import pulpcore.app.models.access_policy
import pulpcore.app.util


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0124_task_deferred_task_immediate"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpenPGPDistribution",
            fields=[
                (
                    "distribution_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.distribution",
                    ),
                ),
            ],
            options={
                "permissions": [
                    ("manage_roles_openpgpdistribution", "Can manage roles on gem distributions")
                ],
                "default_related_name": "%(app_label)s_%(model_name)s",
            },
            bases=("core.distribution", pulpcore.app.models.access_policy.AutoAddObjPermsMixin),
        ),
        migrations.CreateModel(
            name="OpenPGPKeyring",
            fields=[
                (
                    "repository_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.repository",
                    ),
                ),
            ],
            options={
                "permissions": [
                    ("modify_openpgpkeyring", "Can modify content of the keyring"),
                    ("manage_roles_openpgpkeyring", "Can manage roles on keyrings"),
                    ("repair_openpgpkeyring", "Can repair repository versions"),
                ],
                "default_related_name": "%(app_label)s_%(model_name)s",
            },
            bases=("core.repository", pulpcore.app.models.access_policy.AutoAddObjPermsMixin),
        ),
        migrations.CreateModel(
            name="OpenPGPPublicKey",
            fields=[
                (
                    "content_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.content",
                    ),
                ),
                ("raw_data", models.BinaryField()),
                ("fingerprint", models.CharField(max_length=64)),
                ("created", models.DateTimeField()),
                (
                    "_pulp_domain",
                    models.ForeignKey(
                        default=pulpcore.app.util.get_domain_pk,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="core.domain",
                    ),
                ),
            ],
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "unique_together": {("_pulp_domain", "fingerprint")},
            },
            bases=("core.content",),
        ),
        migrations.CreateModel(
            name="OpenPGPUserID",
            fields=[
                (
                    "content_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.content",
                    ),
                ),
                ("raw_data", models.BinaryField()),
                ("user_id", models.CharField()),
                (
                    "public_key",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="user_ids",
                        to="core.openpgppublickey",
                    ),
                ),
            ],
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "unique_together": {("public_key", "user_id")},
            },
            bases=("core.content",),
        ),
        migrations.CreateModel(
            name="OpenPGPUserAttribute",
            fields=[
                (
                    "content_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.content",
                    ),
                ),
                ("raw_data", models.BinaryField()),
                ("sha256", models.CharField(max_length=128)),
                (
                    "public_key",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="user_attributes",
                        to="core.openpgppublickey",
                    ),
                ),
            ],
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "unique_together": {("public_key", "sha256")},
            },
            bases=("core.content",),
        ),
        migrations.CreateModel(
            name="OpenPGPSignature",
            fields=[
                (
                    "content_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.content",
                    ),
                ),
                ("raw_data", models.BinaryField()),
                ("sha256", models.CharField(max_length=128)),
                ("signature_type", models.PositiveSmallIntegerField()),
                ("created", models.DateTimeField()),
                ("expiration_time", models.DurationField(null=True)),
                ("key_expiration_time", models.DurationField(null=True)),
                ("issuer", models.CharField(max_length=16, null=True)),
                ("signers_user_id", models.CharField(null=True)),
                (
                    "signed_content",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="openpgp_signatures",
                        to="core.content",
                    ),
                ),
            ],
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "unique_together": {("signed_content", "sha256")},
            },
            bases=("core.content",),
        ),
        migrations.CreateModel(
            name="OpenPGPPublicSubkey",
            fields=[
                (
                    "content_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="core.content",
                    ),
                ),
                ("raw_data", models.BinaryField()),
                ("fingerprint", models.CharField(max_length=64)),
                ("created", models.DateTimeField()),
                (
                    "public_key",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="public_subkeys",
                        to="core.openpgppublickey",
                    ),
                ),
            ],
            options={
                "default_related_name": "%(app_label)s_%(model_name)s",
                "unique_together": {("public_key", "fingerprint")},
            },
            bases=("core.content",),
        ),
    ]
