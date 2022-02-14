import collections
import itertools

from django.conf import settings
from django.core import mail
from django.core.management.base import BaseCommand

from review.adapter import ApplicationAdapter


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


class ApplicationEmailCommand(BaseCommand):

    default_reply_to_email = getattr(settings, 'APPLICATION_REPLY_TO_EMAIL', ())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = ApplicationAdapter()

    def make_message(self, template_prefix, email, context, cc=None, reply_to=None):
        # allauth really dragging their feet on exposing EmailMessage interface...
        #
        # headers, at least, added; but, only yet in master.
        # regardless, we need access to cc and reply_to.
        #
        # (Note: setting cc/bcc only in headers modifies *only* the headers.
        # We also need to populate recipients() for the server, which checks
        # attributes: to, cc and bcc.)
        #
        # for now, we'll add in extras after the fact:
        #
        msg = self.adapter.render_mail(template_prefix, email, context)

        msg.reply_to.extend(self.default_reply_to_email if reply_to is None else reply_to)

        if cc is not None:
            msg.cc.extend(cc)

        return msg

    def send_mail(self, *args, **kwargs):
        msg = self.make_message(*args, **kwargs)
        msg.send()

    def generate_messages(self, items):
        for item in items:
            yield self.make_message(*item)

    def send_mass_mail(self, items):
        with mail.get_connection() as connection:
            return connection.send_messages(self.generate_messages(items))

    def send_batched_mail(self, items, size=30):
        send_count = 0

        with mail.get_connection() as connection:
            for batch in split_every(items, size):
                send_count += connection.send_messages(self.generate_messages(batch))

        return send_count
