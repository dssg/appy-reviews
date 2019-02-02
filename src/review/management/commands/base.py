from allauth.account.adapter import get_adapter
from django.conf import settings
from django.core.management.base import BaseCommand


class UnbrandedEmailCommand(BaseCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = get_adapter(None)

    def send_mail(self, template, address, context):
        assert not hasattr(settings, 'ACCOUNT_EMAIL_SUBJECT_PREFIX')
        try:
            # NOTE: This could be done, perhaps better, a number of ways,
            # such as configuring a special adapter, or not using the adapter at all.
            # (The adapter in theory does some nice things, but really not required for this.)
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX = ''

            self.adapter.send_mail(template, address, context)
        finally:
            try:
                delattr(settings, 'ACCOUNT_EMAIL_SUBJECT_PREFIX')
            except AttributeError:
                pass
