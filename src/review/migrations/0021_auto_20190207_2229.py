# Generated by Django 2.1.5 on 2019-02-07 22:29

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0020_auto_20190207_2205'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reviewerconcession',
            name='reviewer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', related_query_name='concessions', to=settings.AUTH_USER_MODEL),
        ),
    ]
