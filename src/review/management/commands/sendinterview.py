import argparse
import collections
import enum
import itertools
import re

from django.conf import settings
from django.db import connection
from django.db.models.functions import Now
from terminaltables import AsciiTable

from review.models import InterviewAssignment

from . import base


def round_ordinal(n):
    if n == 1:
        return 'first'
    if n == 2:
        return 'second'
    raise ValueError(n)


INCLUDE = 0
EXCLUDE = 1

def split_every(iterable, n, remainder=INCLUDE):
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

    if remainder == INCLUDE:
        predicate = bool
    elif remainder == EXCLUDE:
        predicate = lambda item: len(item) == n
    else:
        raise TypeError(f"unsupported: {remainder}")

    return itertools.takewhile(predicate, stream)

split_every.INCLUDE = INCLUDE
split_every.EXCLUDE = EXCLUDE


def igetitems(iterable, arg):
    for item in iterable:
        yield item[arg]


EMAIL_PATTERN = re.compile(
    r'''(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"'''
    r'''(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")'''
    r'''@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|'''
    r'''\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|'''
    r'''[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|'''
    r'''\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])''',
    re.I
)

EMAIL_RECIPIENT_PATTERN = re.compile(r'([^ <>]+) +([^ <>]+) *<([^>]+)>')


RecipientBase = collections.namedtuple(
    'RecipientBase',
    ('first_name', 'last_name', 'email')
)

InterviewerBase = collections.namedtuple(
    'InterviewerBase',
    RecipientBase._fields + ('association',)
)


class RecipientMixin:

    email_pattern = EMAIL_PATTERN
    email_recipient_pattern = EMAIL_RECIPIENT_PATTERN

    @classmethod
    def from_signature(cls, value):
        recipient_match = cls.email_recipient_pattern.search(value)
        if not recipient_match:
            raise argparse.ArgumentTypeError(
                f"signature must match: {cls.email_recipient_pattern.pattern}"
            )

        (recipient_first, recipient_last, recipient_email) = recipient_match.groups()

        email_match = cls.email_pattern.search(recipient_email)
        if not email_match:
            raise argparse.ArgumentTypeError("malformed email address")

        return cls(recipient_first, recipient_last, recipient_email)

    @staticmethod
    def make_signature(recipient):
        return f'{recipient.first_name} {recipient.last_name} <{recipient.email}>'

    @property
    def signature(self):
        return self.make_signature(self)


class Recipient(RecipientMixin, RecipientBase):
    pass


class Interviewer(RecipientMixin, InterviewerBase):
    pass


class EmailTemplate(str, enum.Enum):

    initial = 'review/email/interview_assignment_initial'
    final = 'review/email/interview_assignment_final'

    @classmethod
    def for_round(cls, interview_round):
        return cls.initial if interview_round <= 1 else cls.final


class Command(base.UnbrandedEmailCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '--round',
            dest='interview_round',
            type=int,
            choices=tuple(map(int, InterviewAssignment.InterviewRound)),
            help="round of interview assignments to consider (default: all)",
        )
        parser.add_argument(
            '--dry-run',
            action='store_false',
            default=True,
            dest='send_mail',
            help="disable sending mail (just report)",
        )
        parser.add_argument(
            '--test-email',
            action='append',
            dest='test_recipients',
            type=Recipient.from_signature,
            metavar='RECIPIENT',
            help="send tests to provided email signatures: "
                 "First Last <email@domain.com>",
        )

    def get_all_reviewers(self):
        with connection.cursor() as cursor:
            cursor.execute(f'''\
                select "Field1" as first_name,
                       "Field2" as last_name,
                       "Field3" as email,
                       "Field4" as association
                from survey_reviewer_{settings.REVIEW_PROGRAM_YEAR}
            ''')

            for row in cursor:
                yield Interviewer(*row)

    def get_recipients(self, interview_round=None):
        assignments_queryset = InterviewAssignment.objects.current_year().filter(notified=None)

        if interview_round is not None:
            assignments_queryset = assignments_queryset.filter(interview_round=interview_round)

        all_reviewers = {
            reviewer.email.lower(): reviewer
            for reviewer in self.get_all_reviewers()
        }

        for assignment in (
            assignments_queryset.select_related('application__applicant', 'reviewer').iterator()
        ):
            # FIXME: applicant only has email address, and application is just a link
            # FIXME: to survey data; so retrieve full applicant info from survey data
            survey0 = assignment.application.applicationpage_set.all()[0]

            # survey field names are reused; depends on the fact that applicant's
            # vital data come first:
            applicant_info = [survey0.entry.getlist(field)[0]
                              for field in ('First', 'Last', 'Email')]

            # FIXME: loadapps doesn't fill in reviewer name, and so this isn't
            # FIXME: reliably filled in.
            #
            # FIXME: moreover, we don't load reviewer history from the survey at all.
            # FIXME: (since this may change over time, perhaps could be thrown
            # FIXME: onto the ReviewerConcession?)
            #
            # We'll preload these for efficiency.
            interviewer_email = assignment.reviewer.email
            try:
                interviewer = all_reviewers[interviewer_email.lower()]
            except KeyError:
                self.stderr.write(
                    f'[WARN] ignoring assignment {assignment.pk} '
                    f'to unregistered reviewer: {interviewer_email}'
                )
                continue

            yield (
                Recipient(*applicant_info),
                interviewer,
                assignment.interview_round,
                assignment,
            )

    def get_test_recipients(self, test_recipients, interview_round=None):
        interview_round = interview_round or 1
        recipient_stream = split_every(test_recipients, 2, remainder=EXCLUDE)
        for (applicant, reviewer) in recipient_stream:
            yield (
                applicant,
                Interviewer(*reviewer, association='Test Fellow'),
                interview_round,
                None,
            )

    def send_recipients(self, recipient_stream, batch_size=30):
        total_sent = total_recorded = 0

        # must batch these to avoid email sending API limits
        for recipients in split_every(recipient_stream, batch_size):
            try:
                send_count = self.send_mass_mail(
                    (
                        EmailTemplate.for_round(interview_round),               # email template
                        applicant.email,                                        # to: address
                        {                                                       # template context
                            'applicant': applicant,
                            'interviewer': reviewer,
                            'program_year': settings.REVIEW_PROGRAM_YEAR,
                            'round_ordinal': round_ordinal(interview_round),
                            'previous_round_ordinal': (
                                round_ordinal(interview_round - 1) if interview_round > 1 else None
                            ),
                        },
                        (                                                       # cc: addresses
                            reviewer.email,
                            'info@datascienceforsocialgood.org',
                        ),
                    )
                    for (applicant, reviewer, interview_round) in igetitems(recipients, slice(3))
                )
            except Exception:
                failed_emails = (applicant.email for applicant in igetitems(recipients, 0))
                self.stderr.write('[FATAL] send to: ' + ' '.join(failed_emails))
                raise

            total_sent += send_count
            self.stdout.write(f'[INFO] sent {send_count}')

            pks_notified = [assignment.pk for assignment in igetitems(recipients, 3) if assignment]
            if pks_notified:
                assignments_notified = InterviewAssignment.objects.filter(pk__in=pks_notified)
                update_count = assignments_notified.update(notified=Now())
            else:
                update_count = 0

            total_recorded += update_count
            self.stdout.write(f'[INFO] recorded {update_count}')

        self.stdout.write(f'[INFO] totals: sent {total_sent} and recorded {total_recorded}')
        self.stdout.write('[INFO] done')

    def report_recipients(self, recipient_stream):
        table = AsciiTable(
            [('WOULD email', 'with reviewer CC')] +
            [
                (
                    applicant.signature,
                    f'{reviewer.signature} ({reviewer.association})',
                )
                for (applicant, reviewer, _round, _assignment) in recipient_stream
            ],
            'DRY RUN',
        )
        self.stdout.write(table.table)

    def handle(self, interview_round, send_mail, test_recipients, **options):
        if test_recipients:
            recipients = self.get_test_recipients(test_recipients, interview_round)
        else:
            recipients = self.get_recipients(interview_round)

        if send_mail:
            self.send_recipients(recipients)
        else:
            self.report_recipients(recipients)
