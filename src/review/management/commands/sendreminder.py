import argparse
import datetime
import sys

from django.conf import settings
from django.db import connection
from django.utils.safestring import mark_safe

from . import APPLICANT_SURVEY_FIELDS, REFERENCE_FORM_URL
from .base import UnbrandedEmailCommand


APPLICANT_JESSE = ('Applicant Jesse', 'Applicant London', 'jesselondon@gmail.com')
APPLICANT_RAYID = ('Applicant Rayid', 'Applicant Ghani', 'rayidghani@gmail.com')


APPLICATION_FORM2_URL = ('https://datascience.wufoo.com/forms/'
                         f'{settings.REVIEW_PROGRAM_YEAR}-dssg-fellowship-application-part-2/'
                         'def/field461={app_email}')

VALID_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def valid_datetime(value):
    try:
        return datetime.datetime.strptime(value, VALID_DATETIME_FORMAT)
    except ValueError:
        pass

    raise argparse.ArgumentTypeError(f"Invalid date: '{value}'.")


class Command(UnbrandedEmailCommand):

    help = "Send reminder emails to applicants or to applicants' references"

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help="send test emails to Jesse & Rayid",
        )
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true',
            help="do not actually send email",
        )

        subparsers = parser.add_subparsers(dest='target')
        subparsers.required = True

        applicants_description = 'remind applicants to complete their unfinished applications'
        applicants_parser = subparsers.add_parser(
            'applicant',
            description=applicants_description,
            help=applicants_description,
        )
        applicants_parser.add_argument(
            '-t', '--template',
            default='review/email/applicant_reminder',
            help="email template prefix "
                 "(default: review/email/applicant_reminder)",
        )

        references_description = ('remind references to submit their letters '
                                  '(whether submitted or not)')
        references_parser = subparsers.add_parser(
            'reference',
            description=references_description,
            help=references_description,
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

    def handle(self, target, template, test, dry_run, verbosity, since=None, **_options):
        data_handler = getattr(self, f'stream_{target}s')

        for ((app_first, app_last, app_email), reminder_targets) in data_handler(since=since,
                                                                                 test=test):
            if not app_first or not app_last or not app_email:
                print("WARNING: skipping malformed applicant",
                      repr(app_first), repr(app_last), repr(app_email), file=sys.stderr)
                continue

            if verbosity >= 2:
                action = 'WOULD mail (dry run)' if dry_run else 'emailing'
                print(
                    "on behalf of:" if target == 'reference' else f'{action}:',
                    app_first,
                    app_last,
                    f"({app_email})",
                )
                if target == 'reference':
                    print(f"    {action}:", ' and '.join(ref[2] for ref in reminder_targets))

            application_link = mark_safe(APPLICATION_FORM2_URL.format(app_email=app_email))
            reference_link = mark_safe(REFERENCE_FORM_URL.format(app_email=app_email))

            for (target_first, target_last, target_email) in reminder_targets:
                if not target_last or not target_email:
                    if target_first or target_last or target_email:
                        print("WARNING: skipping malformed reminder target",
                              repr(app_first), repr(app_last), repr(app_email), file=sys.stderr)
                    continue

                if dry_run:
                    continue

                self.send_mail(template, target_email, {
                    'applicant_first': app_first,
                    'applicant_last': app_last,
                    'target_first': target_first,
                    'target_last': target_last,
                    'application_link': application_link,
                    'reference_link': reference_link,
                    'program_year': settings.REVIEW_PROGRAM_YEAR,
                })

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
            for (label, field_name) in APPLICANT_SURVEY_FIELDS[:3]
        )
        assert select_fields

        (join_label, join_field) = APPLICANT_SURVEY_FIELDS[2]
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
            f'survey_1."{field_name}" AS {label}'
            for (label, field_name) in APPLICANT_SURVEY_FIELDS
        )
        assert select_fields

        statement = f"""\
            SELECT {select_fields}
            FROM survey_application_1_{settings.REVIEW_PROGRAM_YEAR} AS survey_1
        """
        if since is not None:
            statement += f"""\
                WHERE CAST(survey_1."DateCreated" as timestamp) > %s
            """

        with connection.cursor() as cursor:
            cursor.execute(statement, [since])
            for row in cursor:
                yield (
                    row[:3],            # applicant info
                    (                   # references
                        row[3:6],
                        row[6:],
                    ),
                )
