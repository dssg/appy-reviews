import allauth.account.adapter
from django.conf import settings


class ApplicationAdapter(allauth.account.adapter.DefaultAccountAdapter):

    period_prefix = getattr(settings, 'APPLICATION_EMAIL_SUBJECT_PREFIX', '')

    def format_email_subject(self, subject):
        return f'{self.period_prefix}{subject}'
