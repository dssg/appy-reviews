# Generated by Django 2.0 on 2018-01-31 05:15
from django.db import migrations, models
import review.models


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0005_auto_20180131_0500'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='rating',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='rating',
            name='review',
        ),
        migrations.DeleteModel(
            name='Rating',
        ),

        migrations.AlterField(
            model_name='review',
            name='communication_rating',
            field=models.IntegerField(default=None, verbose_name='Communication Ability'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='review',
            name='data_handling_rating',
            field=models.IntegerField(default=None, verbose_name='Data Handling/Manipulation Skills'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='review',
            name='interest_in_good_rating',
            field=models.IntegerField(default=None, verbose_name='Interest in Social Good'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='review',
            name='machine_learning_rating',
            field=models.IntegerField(default=None, verbose_name='Stats/Machine Learning Ability'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='review',
            name='overall_recommendation',
            field=review.models.EnumCharField([('accept', 'Accept'), ('reject', 'Reject'), ('only_if', 'Only if you need a certain type of fellow (explain below)')], default=None, help_text='Overall recommendation'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='review',
            name='programming_rating',
            field=models.IntegerField(default=None, verbose_name='Programming Ability'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='review',
            name='teamwork_rating',
            field=models.IntegerField(default=None, verbose_name='Would this person work well in a team?'),
            preserve_default=False,
        ),
    ]