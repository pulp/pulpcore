# Generated by Django 3.2.13 on 2022-05-11 21:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0088_accesspolicy_queryset_scoping'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='contentredirectcontentguard',
            options={'default_related_name': '%(app_label)s_%(model_name)s', 'permissions': (('manage_roles_contentredirectcontentguard', 'Can manage role assignments on Redirect content guard'),)},
        ),
    ]
