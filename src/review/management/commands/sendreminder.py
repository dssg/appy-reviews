import argparse
import datetime
import sys

from allauth.account.adapter import get_adapter
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.safestring import mark_safe


APPLICANT_JESSE = ('Applicant Jesse', 'Applicant London', 'jesselondon@gmail.com')
APPLICANT_RAYID = ('Applicant Rayid', 'Applicant Ghani', 'rayidghani@gmail.com')


SURVEY_FIELDS = (
    ('app_first', 'Field451'),
    ('app_last', 'Field452'),
    ('app_email', 'Field461'),
    ('ref0_first', 'Field668'),
    ('ref0_last', 'Field669'),
    ('ref0_email', 'Field670'),
    ('ref1_first', 'Field671'),
    ('ref1_last', 'Field672'),
    ('ref1_email', 'Field673'),
)

APPLICATION_FORM2_URL = ('https://datascience.wufoo.com/forms/'
                         '2019-dssg-fellowship-application-part-2/def/field461={app_email}')

REFERENCE_FORM_URL = ('https://datascience.wufoo.com/forms/'
                      '?formname=2019-dssg-fellow-recommendation-form&field461={app_email}')

VALID_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def valid_datetime(value):
    try:
        return datetime.datetime.strptime(value, VALID_DATETIME_FORMAT)
    except ValueError:
        pass

    raise argparse.ArgumentTypeError(f"Invalid date: '{value}'.")


class Command(BaseCommand):

    help = "Send reminder emails to applicants or to applicants' references"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = get_adapter(None)

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help="send test emails to Jesse & Rayid",
        )

        subparsers = parser.add_subparsers(dest='target')
        subparsers.required = True

        applicants_parser = subparsers.add_parser(
            'applicant',
            description='remind applicants to complete their applications',
            help='remind applicants to complete their applications',
        )
        applicants_parser.add_argument(
            '-t', '--template',
            default='review/email/applicant_reminder',
            help="email template prefix "
                 "(default: review/email/applicant_reminder)",
        )

        references_parser = subparsers.add_parser(
            'reference',
            description='remind references to submit their letters',
            help='remind references to submit their letters',
        )
        references_parser.add_argument(
            '-t', '--template',
            default='review/email/reference_reminder',
            help="email template prefix "
                 "(default: review/email/reference_reminder)",
        )
        references_parser.add_argument(
            '--since',
            metavar='TIMESTAMP',
            type=valid_datetime,
            help="only send reminders to references added to system after "
                 "database-compatible timestamp (e.g.: 2004-10-19T10:23:54)",
        )

    def handle(self, target, template, test, verbosity, since=None, **_options):
        data_handler = getattr(self, f'stream_{target}s')

        for ((app_first, app_last, app_email), reminder_targets) in data_handler(since=since,
                                                                                 test=test):
            if not app_first or not app_last or not app_email:
                print("WARNING: skipping malformed applicant",
                      repr(app_first), repr(app_last), repr(app_email), file=sys.stderr)
                continue

            if verbosity >= 2:
                print(
                    "on behalf of:" if target == 'reference' else 'emailing:',
                    app_first,
                    app_last,
                    f"({app_email})",
                )
                if target == 'reference':
                    print("    emailing:", ' and '.join(ref[2] for ref in reminder_targets))

            for (target_first, target_last, target_email) in reminder_targets:
                if not target_last or not target_email:
                    if target_first or target_last or target_email:
                        print("WARNING: skipping malformed reminder target",
                              repr(app_first), repr(app_last), repr(app_email), file=sys.stderr)
                    continue

                self.send_mail(
                    template,
                    target_email,
                    target_first,
                    target_last,
                    app_email,
                    app_first,
                    app_last,
                )

    @staticmethod
    def stream_applicants(since=None, test=False):
        if since is not None:
            raise NotImplementedError

        if test:
            # (applicant info, target infos)
            yield (APPLICANT_JESSE, [APPLICANT_JESSE])
            yield (APPLICANT_RAYID, [APPLICANT_RAYID])

            return

        select_fields = ', '.join(
            f'survey_1."{field_name}" AS {label}'
            for (label, field_name) in SURVEY_FIELDS[:3]
        )
        assert select_fields

        (join_label, join_field) = SURVEY_FIELDS[2]
        assert join_label == 'app_email'

        with connection.cursor() as cursor:
            # query info of applicants who are in part-1 but not part-2 of the survey
            cursor.execute(f"""\
                SELECT {select_fields}
                FROM survey_application_1_{settings.REVIEW_PROGRAM_YEAR} AS survey_1
                LEFT OUTER JOIN survey_application_2_{settings.REVIEW_PROGRAM_YEAR} AS survey_2
                USING ("{join_field}")
                WHERE survey_2."{join_field}" IS NULL
            """)
            for row in cursor:
                # (applicant info, [targets: the applicant])
                yield (row, [row])

    @staticmethod
    def stream_references(since=None, test=False):
        if test:
            if since is not None:
                raise NotImplementedError

            yield (
                APPLICANT_JESSE,
                (
                    ('Reference Rayid', 'Reference Ghani', 'rayidghani@gmail.com'),
                    ('Reference Rayid', 'Reference Ghani', 'rayid@uchicago.edu'),
                ),
            )

            yield (
                APPLICANT_RAYID,
                (
                    ('Reference Jesse', 'Reference London', 'jesselondon@gmail.com'),
                    ('Reference Jesse', 'Reference London', 'jslondon@uchicago.edu'),
                ),
            )

            return

        select_fields = ', '.join(
            f'"{field_name}" AS {label}'
            for (label, field_name) in SURVEY_FIELDS
        )
        assert select_fields

        with connection.cursor() as cursor:
            cursor.execute(
                f"""\
                    SELECT {select_fields} FROM survey_application_1_{settings.REVIEW_PROGRAM_YEAR}
                """ + (
                    f"""\
                        WHERE CAST("DateCreated" as timestamp) > %s
                    """ if since is not None else ''
                ),
                [since],
            )
            for row in cursor:
                yield (
                    row[:3],            # applicant info
                    (                   # references
                        row[3:6],
                        row[6:],
                    ),
                )

    def send_mail(
        self, template,
        address, target_first, target_last,
        app_email, app_first, app_last
    ):
        assert not hasattr(settings, 'ACCOUNT_EMAIL_SUBJECT_PREFIX')
        try:
            # NOTE: This could be done, perhaps better, a number of ways,
            # such as configuring a special adapter, or not using the adapter at all.
            # (The adapter in theory does some nice things, but really not required for this.)
            settings.ACCOUNT_EMAIL_SUBJECT_PREFIX = ''

            self.adapter.send_mail(template, address, {
                'applicant_first': app_first,
                'applicant_last': app_last,
                'target_first': target_first,
                'target_last': target_last,
                'application_link': mark_safe(APPLICATION_FORM2_URL.format(app_email=app_email)),
                'reference_link': mark_safe(REFERENCE_FORM_URL.format(app_email=app_email)),
                'program_year': settings.REVIEW_PROGRAM_YEAR,
            })
        finally:
            try:
                delattr(settings, 'ACCOUNT_EMAIL_SUBJECT_PREFIX')
            except AttributeError:
                pass
