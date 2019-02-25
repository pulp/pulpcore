# Generated by Django 2.1.7 on 2019-03-05 23:37

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pulp_app', '0004_upload'),
    ]

    operations = [
        migrations.AddField(
            model_name='distribution',
            name='remote',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='distributions', to='pulp_app.Remote'),
        ),
    ]
