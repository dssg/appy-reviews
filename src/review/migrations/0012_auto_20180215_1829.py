# Generated by Django 2.0 on 2018-02-15 18:29
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0011_auto_20180214_2043'),
    ]

    operations = [
        migrations.RenameModel('Review', 'ApplicationReview'),
        migrations.AlterModelOptions(
            name='applicationreview',
            options={'ordering': ('-submitted',)},
        ),
        migrations.AlterField(
            model_name='applicationreview',
            name='application',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='application_reviews', to='review.Application'),
        ),
        migrations.AlterField(
            model_name='applicationreview',
            name='reviewer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='application_reviews', to=settings.AUTH_USER_MODEL),
        ),
    ]
