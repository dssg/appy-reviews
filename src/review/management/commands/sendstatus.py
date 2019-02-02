import itertools
from collections import namedtuple

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection
from django.utils.safestring import mark_safe

from . import APPLICANT_SURVEY_FIELDS, REFERENCE_SURVEY_FIELDS, REFERENCE_FORM_URL
from .base import UnbrandedEmailCommand


class Command(UnbrandedEmailCommand):

    help = "Send final status emails to applicants and reminders to unsubmitted references"

    def add_arguments(self, parser):
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
            dest='test_emails',
            metavar='EMAIL',
            help="send tests to provided emails",
        )
        parser.add_argument(
            '--debug-sql',
            action='store_true',
            help="print underlying SQL statement",
        )

        parser.add_argument(
            '--incomplete',
            action='store_true',
            help="notify applicants who did not complete their applications",
        )
        parser.add_argument(
            '--unsubmitted',
            action='store_true',
            help="notify applicants with completed applications but less than "
                 "two references",
        )
        parser.add_argument(
            '--complete',
            action='store_true',
            help="notify applicants with completed applications and at least "
                 "two references",
        )
        parser.add_argument(
            '--all-applicants',
            action='store_true',
            help="notify all applicants of their statuses",
        )

        parser.add_argument(
            '--references',
            action='store_true',
            help="notify recommenders who haven't submitted references for "
                 "applicants with completed applications",
        )

    def send_mail(self, template, address, context, on_behalf=None):
        action_text = 'emailed' if self._send_mail else 'would-email'
        log_args = (action_text, address)
        if on_behalf:
            log_args += ('on-behalf-of', on_behalf)

        if self._send_mail:
            super().send_mail(template, address, context)
            if self._verbosity > 1:
                print(*log_args)
        else:
            # print(on_behalf, address)  # TODO: perhaps add --debug-log option to output like this
            print(*log_args)

    def handle(self, incomplete, unsubmitted, complete, all_applicants, references, send_mail,
               test_emails, debug_sql, verbosity, **_opts):
        self._send_mail = send_mail
        self._verbosity = verbosity

        if debug_sql:
            print(sql_statement())
            return

        if incomplete or unsubmitted or complete or all_applicants:
            # This is intended largely for them; but, Rayid handled this, this year
            raise NotImplementedError

        if all_applicants and (incomplete or unsubmitted or complete):
            raise CommandError("redundant argumentation")

        if all_applicants:
            incomplete = unsubmitted = complete = True

        if not incomplete and not unsubmitted and not complete and not references:
            raise CommandError("nothing to do")

        results = stream_test(test_emails) if test_emails else stream_applications()
        for result in results:
            if not result.app_completed:
                if incomplete:
                    raise NotImplementedError

                # nothing more to do with incomplete applications
                continue

            references_submitted = (result.ref0_submitted, result.ref1_submitted)
            if not all(references_submitted):
                if references:
                    app_references = (result[3:6], result[6:9])
                    reference_link = REFERENCE_FORM_URL.format(app_email=result.app_email)

                    for ((ref_first,
                          ref_last,
                          ref_email),
                         reference_submitted) in zip(app_references, references_submitted):
                        if not reference_submitted:
                            self.send_mail(
                                'review/email/reference_status',
                                ref_email,
                                {
                                    'applicant_first': result.app_first,
                                    'applicant_last': result.app_last,
                                    'ref_first': ref_first,
                                    'ref_last': ref_last,
                                    'reference_link': mark_safe(reference_link),
                                    'program_year': settings.REVIEW_PROGRAM_YEAR,
                                },
                                on_behalf=result.app_email,
                            )

            if len(result.references) < 2:
                if unsubmitted:
                    raise NotImplementedError

            else:
                if complete:
                    raise NotImplementedError


def sql_statement():
    select_fields = ', '.join(
        f'survey_1."{field_name}" AS {label}'
        for (label, field_name) in APPLICANT_SURVEY_FIELDS
    )
    assert select_fields

    applicant_fields = dict(APPLICANT_SURVEY_FIELDS)
    reference_fields = dict(REFERENCE_SURVEY_FIELDS)

    ref_first = reference_fields['ref_first']
    ref_last = reference_fields['ref_last']
    ref_email = reference_fields['ref_email']
    app_email = applicant_fields['app_email']
    ref0_email = applicant_fields['ref0_email']
    ref1_email = applicant_fields['ref1_email']

    return f"""\
        WITH application_status AS (
                SELECT DISTINCT {select_fields}, (
                    CASE WHEN survey_2."{app_email}" IS NULL THEN false ELSE true END
                ) as app_completed, (
                    CASE WHEN rec_j0."{ref_email}" IS NULL THEN false ELSE true END
                ) as ref0_submitted, (
                    CASE WHEN rec_j1."{ref_email}" IS NULL THEN false ELSE true END
                ) as ref1_submitted
                FROM survey_application_1_{settings.REVIEW_PROGRAM_YEAR} AS survey_1
                LEFT OUTER JOIN survey_application_2_{settings.REVIEW_PROGRAM_YEAR} AS survey_2 ON(
                    LOWER(survey_1."{app_email}") = LOWER(survey_2."{app_email}")
                )
                LEFT OUTER JOIN survey_recommendation_{settings.REVIEW_PROGRAM_YEAR} AS rec_j0 ON (
                    LOWER(survey_1."{ref0_email}") = LOWER(rec_j0."{ref_email}") AND
                    LOWER(survey_1."{app_email}") = LOWER(rec_j0."{app_email}")
                )
                LEFT OUTER JOIN survey_recommendation_{settings.REVIEW_PROGRAM_YEAR} rec_j1 ON (
                    LOWER(survey_1."{ref1_email}") = LOWER(rec_j1."{ref_email}") AND
                    LOWER(survey_1."{app_email}") = LOWER(rec_j1."{app_email}")
                )
            ),
            application_reference AS (
                SELECT DISTINCT ON (LOWER("{app_email}"), LOWER("{ref_email}"))
                       "{app_email}" AS app_email, "{ref_email}" AS ref_email,
                       "{ref_first}" AS ref_first, "{ref_last}" AS ref_last
                FROM survey_recommendation_{settings.REVIEW_PROGRAM_YEAR}
            ),
            reference_aggregate AS (
                SELECT LOWER(app_email) AS app_email,
                       ARRAY_AGG(ARRAY[ref_first, ref_last, ref_email]) AS references
                FROM application_reference
                GROUP BY 1
            )

        SELECT application_status.*,
               COALESCE(reference_aggregate.references, ARRAY[]::TEXT[]) as references
        FROM application_status
        LEFT OUTER JOIN reference_aggregate ON (
            LOWER(application_status.app_email) = LOWER(reference_aggregate.app_email)
        )
    """


ApplicationStatus = namedtuple(
    'ApplicationStatus',
    [label for (label, _col_name) in APPLICANT_SURVEY_FIELDS] +
    [
        'app_completed',
        'ref0_submitted',
        'ref1_submitted',
        'references',
    ]
)


def stream_applications():
    statement = sql_statement()
    with connection.cursor() as cursor:
        cursor.execute(statement)
        for row in cursor:
            yield ApplicationStatus._make(row)


def stream_test(emails):
    email_stream = iter(emails)
    for count in itertools.count():
        try:
            yield ApplicationStatus(
                f'Applicant {count} First',
                f'Applicant {count} Last',
                next(email_stream),
                f'Reference0 {count} First',
                f'Reference0 {count} Last',
                next(email_stream),
                f'Reference1 {count} First',
                f'Reference1 {count} Last',
                next(email_stream),
                True,
                True,
                False,
                [],
            )
        except StopIteration:
            break
