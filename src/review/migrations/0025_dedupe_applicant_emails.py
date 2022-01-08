from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower


def dedupe_applicant_emails(apps, schema_editor):
    Applicant = apps.get_model('review', 'Applicant')

    emails_lowered = Applicant.objects.annotate(email_lower=Lower('email')).values('email_lower')
    emails_grouped = emails_lowered.annotate(email_count=Count('email_lower'))

    for email_dupe in emails_grouped.filter(email_count__gt=1).values_list('email_lower', flat=True).iterator():
        (applicant, *applicant_dupes) = Applicant.objects.filter(email__iexact=email_dupe).order_by('created').iterator()

        for applicant_dupe in applicant_dupes:
            applicant_dupe.applications.update(applicant=applicant)
            applicant_dupe.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0024_auto_20200214_1941'),
    ]

    operations = [
        migrations.RunPython(dedupe_applicant_emails),
    ]
