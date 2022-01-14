import collections
import contextlib
import itertools

from allauth.account.adapter import get_adapter
from django.conf import settings
from django.core import mail
from django.core.management.base import BaseCommand


_INCLUDE = 0
_EXCLUDE = 1

def split_every(iterable, n, remainder=_INCLUDE):
    """Slice an iterable into batches/chunks of n elements

    Each generated chunk is of type tuple.

    :type iterable: Iterable
    :type n: int
    :type remainder: int
    :rtype: Iterator

    """
    iterator = iter(iterable)
    stream = (tuple(itertools.islice(iterator, n))
              for _none in itertools.repeat(None))

    if remainder == _INCLUDE:
        predicate = bool
    elif remainder == _EXCLUDE:
        predicate = lambda item: len(item) == n
    else:
        raise TypeError(f"unsupported: {remainder}")

    return itertools.takewhile(predicate, stream)

split_every.INCLUDE = _INCLUDE
split_every.EXCLUDE = _EXCLUDE


def exhaust_iterable(iterable):
    collections.deque(iterable, maxlen=0)


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

    def send_batched_email(self, data, size=30):
        send_count = 0

        for items in split_every(data, size):
            send_count += self.send_mass_mail(items)

        return send_count
