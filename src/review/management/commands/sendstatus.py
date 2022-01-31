import itertools
import urllib
from collections import defaultdict, namedtuple

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection, IntegrityError
from django.utils.safestring import mark_safe

from review import models

from . import APPLICANT_SURVEY_FIELDS, REFERENCE_SURVEY_FIELDS, REFERENCE_FORM_URL
from .base import ApplicationEmailCommand, exhaust_iterable


class Command(ApplicationEmailCommand):

    help = ("Send final status emails to applicants and "
            "reminders to unsubmitted references")

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
            dest='opt_incomplete',
            help="warn applicants who did not complete their applications (UNIMPLEMENTED)",
        )
        parser.add_argument(
            '--unsubmitted',
            action='store_true',
            dest='opt_unsubmitted',
            help="warn applicants with completed applications but less than "
                 "two references (template: review/email/applicant_references)",
        )
        parser.add_argument(
            '--submitted',
            action='store_true',
            dest='opt_submitted',
            help="notify applicants with completed applications and at least "
                 "two references "
                 "(note: will never send more than once per application) "
                 "(template: review/email/applicant_complete)",
        )
        parser.add_argument(
            '--all-complete',
            action='store_true',
            dest='opt_complete',
            help="notify all applicants with completed applications "
                 "(regardless of recommendations) "
                 "(template: review/email/applicant_review)",
        )

        parser.add_argument(
            '--references',
            action='store_true',
            dest='opt_references',
            help="warn recommenders who haven't submitted references for "
                 "applicants (regardless of application completion: see "
                 "--references-complete)",
        )
        parser.add_argument(
            '--references-complete',
            action='store_true',
            dest='opt_references_complete',
            help="do NOT email recommender if their applicant hasn't yet "
                 "completed their application",
        )
        parser.add_argument(
            '--references-template',
            dest='opt_references_template',
            default='review/email/reference_reminder',
            metavar='PATH',
            help="reference email template prefix "
                 "(default: review/email/reference_reminder)",
        )
        parser.add_argument(
            '--references-late',
            dest='opt_references_template',
            action='store_const',
            const='review/email/reference_status',
            help="use post-deadline reference email template "
                 "(prefix: review/email/reference_status)",
        )

    def handle(self, opt_incomplete, opt_unsubmitted, opt_submitted, opt_complete,
               opt_references, opt_references_complete, opt_references_template,
               send_mail, test_emails, debug_sql, verbosity, **_opts):
        self._create_cache = defaultdict(list)
        self._verbosity = verbosity

        if debug_sql:
            print(sql_statement())
            return

        if opt_incomplete:
            # This was intended largely for them; but, Rayid handled these, this year
            raise NotImplementedError

        if (not opt_incomplete and not opt_unsubmitted and not opt_submitted and
            not opt_complete and not opt_references):
            raise CommandError("nothing to do")

        application_statuses = stream_test(test_emails) if test_emails else stream_applications()

        to_mail = self.generate_mail(application_statuses,
                                     opt_incomplete, opt_unsubmitted,
                                     opt_submitted, opt_complete,
                                     opt_references, opt_references_complete,
                                     opt_references_template)

        messages = self.process_mail(to_mail, send_mail=send_mail)

        if send_mail:
            send_count = self.send_batched_mail(messages)
            self.stderr.write(f'I: sent {send_count}')

            for (model, objs) in self._create_cache.items():
                if objs:
                    try:
                        model.objects.bulk_create(objs, ignore_conflicts=True)
                    except IntegrityError as exc:
                        batch_ids = [obj.application_id for obj in objs]
                        self.stderr.write(
                            f'E: integrity error affecting batch {model.__name__} '
                            f'application_id={batch_ids}: {exc}'
                        )
                    else:
                        self.stderr.write(f'I: inserted {len(objs)} ({model._meta.db_table})')
        else:
            exhaust_iterable(messages)

    def process_mail(self, messages, send_mail):
        # It's *possible* to send duplicate emails (most commonly due to bad,
        # but unavoidable, user data). Try to catch these.
        references_emailed = set()

        for (template, address, context, on_behalf) in messages:
            email_signature = (template, address.lower())  # assumes context unvariable
            if on_behalf:
                email_signature += (on_behalf.lower(),)

            if email_signature in references_emailed:
                self.stderr.write(
                    f"W: duplicate email (will not send) to: {address} for: " +
                    (on_behalf or '<none>')
                )
                continue

            references_emailed.add(email_signature)

            action_text = 'emailed' if send_mail else 'would-email'
            log_args = (action_text, address)
            if on_behalf:
                log_args += ('on-behalf-of', on_behalf)

            if not send_mail or self._verbosity > 1:
                self.stdout.write(' '.join(log_args))

            yield (template, address, context)

    def generate_mail(self, application_statuses,
                      opt_incomplete, opt_unsubmitted,
                      opt_submitted, opt_complete,
                      opt_references, opt_references_complete,
                      opt_references_template):
        for status in application_statuses:
            if not status.app_completed:
                if opt_incomplete:
                    raise NotImplementedError

                if opt_references_complete:
                    # nothing more to do with incomplete applications
                    continue

            reference_link = REFERENCE_FORM_URL.format(
                app_email=urllib.parse.quote_plus(status.app_email),
            )
            references_submitted = (status.ref0_submitted, status.ref1_submitted)
            if not all(references_submitted) and opt_references and (status.app_completed or
                                                                     not opt_references_complete):
                app_references = (status[4:7], status[7:10])

                for ((ref_first,
                      ref_last,
                      ref_email),
                     reference_submitted) in zip(app_references, references_submitted):
                    if not reference_submitted:
                        yield (
                            opt_references_template,
                            ref_email,
                            {
                                'applicant_first': status.app_first,
                                'applicant_last': status.app_last,
                                'ref_first': ref_first,
                                'ref_last': ref_last,
                                'target_first': ref_first,
                                'target_last': ref_last,
                                'reference_link': mark_safe(reference_link),
                                'program_year': settings.REVIEW_PROGRAM_YEAR,
                            },
                            status.app_email,
                        )

            if opt_complete and status.app_completed:
                yield (
                    'review/email/applicant_review',
                    status.app_email,
                    {
                        'applicant_first': status.app_first,
                        'applicant_last': status.app_last,
                        'program_year': settings.REVIEW_PROGRAM_YEAR,
                    },
                    None,
                )

            if len(status.references) < 2:
                if opt_unsubmitted and status.app_completed:
                    yield (
                        'review/email/applicant_references',
                        status.app_email,
                        {
                            'applicant_first': status.app_first,
                            'applicant_last': status.app_last,
                            'reference': status.references[0] if status.references else None,
                            'reference_link': mark_safe(reference_link),
                            'program_year': settings.REVIEW_PROGRAM_YEAR,
                        },
                        None,
                    )

            elif opt_submitted and status.app_completed and not status.email_complete_sent:
                if status.application_id is None:
                    self.stderr.write(f'E: application not found: {status.app_email}')
                else:
                    self._create_cache[models.ApplicationCompleteMessage].append(
                        models.ApplicationCompleteMessage(application_id=status.application_id)
                    )

                    yield (
                        'review/email/applicant_complete',
                        status.app_email,
                        {
                            'applicant_first': status.app_first,
                            'applicant_last': status.app_last,
                            'program_year': settings.REVIEW_PROGRAM_YEAR,
                        },
                        None,
                    )


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
                SELECT DISTINCT page.application_id, {select_fields}, (
                    CASE WHEN survey_2."{app_email}" IS NULL THEN false ELSE true END
                ) as app_completed, (
                    CASE WHEN rec_j0."{ref_email}" IS NULL THEN false ELSE true END
                ) as ref0_submitted, (
                    CASE WHEN rec_j1."{ref_email}" IS NULL THEN false ELSE true END
                ) as ref1_submitted, (
                    CASE WHEN email_complete.email_message_id IS NULL THEN false ELSE true END
                ) as email_complete_sent
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
                LEFT OUTER JOIN application_page page ON (
                    page.table_name = 'survey_application_1_{settings.REVIEW_PROGRAM_YEAR}' AND
                    page.column_name = 'EntryId' AND
                    page.entity_code = survey_1."EntryId"
                )
                LEFT OUTER JOIN application USING (application_id)
                LEFT OUTER JOIN email_message_application_complete email_complete USING (application_id)
                WHERE withdrawn IS NULL
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
    ['application_id'] +
    [label for (label, _col_name) in APPLICANT_SURVEY_FIELDS] +
    [
        'app_completed',
        'ref0_submitted',
        'ref1_submitted',
        'email_complete_sent',
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
            (app_email, ref0_email, ref1_email) = itertools.islice(email_stream, 3)
        except ValueError:
            break
        else:
            (app_completed, ref0_submitted, ref1_submitted) = (True, True, False)

            reference0 = [f'Reference0 {count} First', f'Reference0 {count} Last', ref0_email]
            reference1 = [f'Reference1 {count} First', f'Reference1 {count} Last', ref1_email]

            yield ApplicationStatus(
                0,
                f'Applicant {count} First',
                f'Applicant {count} Last',
                app_email,
                reference0[0],
                reference0[1],
                ref0_email,
                reference1[0],
                reference1[1],
                ref1_email,
                app_completed,
                ref0_submitted,
                ref1_submitted,
                False,
                [
                    ref for (ref, ref_submitted) in (
                        (reference0, ref0_submitted),
                        (reference1, ref1_submitted)
                    ) if ref_submitted
                ],
            )
