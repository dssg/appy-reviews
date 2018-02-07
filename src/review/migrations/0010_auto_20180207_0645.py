# Generated by Django 2.0 on 2018-02-07 06:45

from django.db import migrations, models
import review.models


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0009_auto_20180201_2240'),
    ]

    operations = [
        migrations.AddField(
            model_name='review',
            name='social_science',
            field=models.IntegerField(null=True, verbose_name='Social Science'),
        ),

        migrations.AlterField(
            model_name='review',
            name='comments',
            field=models.TextField(blank=True, help_text='Any comments?'),
        ),
        migrations.AlterField(
            model_name='review',
            name='data_handling_rating',
            field=models.IntegerField(verbose_name='Data Handling & Manipulation'),
        ),
        migrations.AlterField(
            model_name='review',
            name='machine_learning_rating',
            field=models.IntegerField(verbose_name='Stats & Machine Learning'),
        ),
        migrations.AlterField(
            model_name='review',
            name='overall_recommendation',
            field=review.models.EnumCharField([('interview', 'Interview'), ('reject', 'Reject'), ('only_if', 'Interview <em>only</em> if you need a certain type of fellow (explain below)')], help_text='Overall recommendation'),
        ),
        migrations.AlterField(
            model_name='review',
            name='programming_rating',
            field=models.IntegerField(verbose_name='Programming'),
        ),
        migrations.AlterField(
            model_name='review',
            name='teamwork_rating',
            field=models.IntegerField(verbose_name='Teamwork and Collaboration'),
        ),
        migrations.AlterField(
            model_name='review',
            name='would_interview',
            field=models.BooleanField(help_text='If this applicant moves to the interview round, would you like to interview them?'),
        ),
    ]
