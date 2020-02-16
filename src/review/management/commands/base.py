import contextlib

from allauth.account.adapter import get_adapter
from django.conf import settings
from django.core import mail
from django.core.management.base import BaseCommand


@contextlib.contextmanager
def set_email_prefix(prefix):
    assert not hasattr(settings, 'ACCOUNT_EMAIL_SUBJECT_PREFIX')

    try:
        # NOTE: This could be done, perhaps better, a number of ways,
        # such as configuring a special adapter, or not using the adapter at all.
        # (The adapter in theory does some nice things, but really not required for this.)
        settings.ACCOUNT_EMAIL_SUBJECT_PREFIX = prefix
        yield prefix
    finally:
        try:
            delattr(settings, 'ACCOUNT_EMAIL_SUBJECT_PREFIX')
        except AttributeError:
            pass


class UnbrandedEmailCommand(BaseCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = get_adapter(None)

    def send_mail(self, template, address, context):
        with set_email_prefix(''):
            self.adapter.send_mail(template, address, context)

    def _mass_mail_messages(self, data):
        for item in data:
            try:
                (template_prefix, email, context, cc) = item
            except ValueError:
                (template_prefix, email, context) = item
                cc = ()

            msg = self.adapter.render_mail(template_prefix, email, context)
            msg.cc.extend(cc)

            yield msg

    def send_mass_mail(self, data):
        with set_email_prefix(''):
            with mail.get_connection() as connection:
                return connection.send_messages(self._mass_mail_messages(data))
