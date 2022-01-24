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

    @classmethod
    def make_message_args(cls, template_prefix, email, context, cc=None, reply_to=None, headers=None):
        if headers is None:
            headers = {}

        if reply_to is None:
            reply_to = cls.default_reply_to_email

        for (name, value) in (('Cc', cc), ('Reply-To', reply_to)):
            if value:
                headers[name] = value if isinstance(value, str) else ', '.join(value)

        return (template_prefix, email, context, headers)

    def send_mail(self, *args, **kwargs):
        # (see below TODO)
        # message_args = self.make_message_args(*args, **kwargs)
        # msg = self.adapter.render_mail(*message_args)
        (*message_args, headers) = self.make_message_args(*args, **kwargs)
        msg = self.adapter.render_mail(*message_args)
        msg.extra_headers.update(headers)
        msg.send()

    def generate_messages(self, items):
        for item in items:
            # TODO: allauth *really* dragging their feet on exposing EmailMessage interface...
            #
            # headers, at least, added; but, only yet in master.
            #
            # once merged, this should work fine:
            #
            #     message_args = self.make_message_args(*item)
            #     yield self.adapter.render_mail(*message_args)
            #
            # until then, we'll add in headers after the fact:
            #
            (*message_args, headers) = self.make_message_args(*item)
            message = self.adapter.render_mail(*message_args)
            message.extra_headers.update(headers)
            yield message

    def send_mass_mail(self, items):
        with mail.get_connection() as connection:
            return connection.send_messages(self.generate_messages(items))

    def send_batched_mail(self, items, size=30):
        send_count = 0

        for batch in split_every(items, size):
            send_count += self.send_mass_mail(batch)

        return send_count
