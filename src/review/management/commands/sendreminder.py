import sys

from allauth.account.adapter import get_adapter
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.safestring import mark_safe


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

REFERENCE_FORM_URL = ('https://datascience.wufoo.com/forms/'
                      '?formname=2019-dssg-fellow-recommendation-form&field461={app_email}')


class Command(BaseCommand):

    help = "Send emails to applicants' references to remind them to submit"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = get_adapter(None)

    def add_arguments(self, parser):
        parser.add_argument(
            '-t', '--template',
            default='review/email/reference_reminder',
            help="email template prefix "
                 "(default: review/email/reference_reminder)",
        )
        parser.add_argument(
            '--test',
            action='store_true',
            help="send test emails to Jesse & Rayid",
        )

    def handle(self, template, test, verbosity, **_options):
        for ((app_first, app_last, app_email), references) in self.stream_references(test):
            if not app_first or not app_last or not app_email:
                print("WARNING: skipping malformed applicant",
                      repr(app_first), repr(app_last), repr(app_email), file=sys.stderr)
                continue

            if verbosity >= 2:
                print("on behalf of:", app_first, app_last, f"({app_email})")
                print("    emailing:", ' and '.join(ref[2] for ref in references))

            for (ref_first, ref_last, ref_email) in references:
                if not ref_last or not ref_email:
                    if ref_first or ref_last or ref_email:
                        print("WARNING: skipping malformed reference",
                              repr(app_first), repr(app_last), repr(app_email), file=sys.stderr)
                    continue

                self.send_mail(
                    template,
                    ref_email,
                    ref_first,
                    ref_last,
                    app_email,
                    app_first,
                    app_last,
                )

    @staticmethod
    def stream_references(test=False):
        if test:
            yield (
                ('Applicant Jesse', 'Applicant London', 'jesselondon@gmail.com'),
                (
                    ('Reference Rayid', 'Reference Ghani', 'rayidghani@gmail.com'),
                    ('Reference Rayid', 'Reference Ghani', 'rayid@uchicago.edu'),
                ),
            )

            yield (
                ('Applicant Rayid', 'Applicant Ghani', 'rayidghani@gmail.com'),
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
            cursor.execute(f"""\
                SELECT {select_fields} FROM survey_application_1_{settings.REVIEW_PROGRAM_YEAR}
            """)
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
        address, reference_first, reference_last,
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
                'reference_first': reference_first,
                'reference_last': reference_last,
                'reference_link': mark_safe(REFERENCE_FORM_URL.format(app_email=app_email)),
                'program_year': settings.REVIEW_PROGRAM_YEAR,
            })
        finally:
            try:
                delattr(settings, 'ACCOUNT_EMAIL_SUBJECT_PREFIX')
            except AttributeError:
                pass
