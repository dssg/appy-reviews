import argparse

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core import management
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import connection, transaction
from terminaltables import AsciiTable

from review import models


def make_email(value, lower=True):
    try:
        validate_email(value)
    except ValidationError as exc:
        raise argparse.ArgumentTypeError(exc)

    return value.lower() if lower else value


class Command(BaseCommand):

    class DryRunAbort(RuntimeError):
        pass

    help = (
        "Map Wufoo application/survey data into the Review Web application. "
        "Requires that Wufoo data has been loaded into the database. (See command: loadwufoo.)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '-d', '--dry-run',
            action='store_true',
            help="do not commit database transactions so as to test effect "
                 "of command",
        )
        parser.add_argument(
            '-s', '--suffix',
            default=f'_{settings.REVIEW_PROGRAM_YEAR}',
            help="Suffix to apply to the names of survey tables from which command should read. "
                 f"Default: _{settings.REVIEW_PROGRAM_YEAR}. "
                 "E.g.: If the first page of application survey data has been loaded into "
                 "table \"survey_application_1_2018\", then specify \"_2018\".",
        )
        parser.add_argument(
            '--entity-id', '--id',
            default='EntryId',
            metavar='COLUMN',
            dest='entity_id_field',
            help="Survey data column which should be used as an entity identifier and reference."
                 "(Entities are correlated by email regardless.)",
        )
        parser.add_argument(
            '--closed',
            action='store_true',
            help="Treat the fellow application submission period as closed -- "
                 "reviewers will be loaded, but no fellow applications.",
        )
        parser.add_argument(
            '--invite-only',
            action='append',
            metavar='EMAIL',
            type=make_email,
            help="Consider only *these* reviewer records, indicated by email "
                 "address, and do not process any other dataset",
        )
        parser.add_argument(
            '--email-ignore',
            action='append',
            metavar='EMAIL',
            type=make_email,
            help="Do not email these reviewers, indicated by email address, "
                 "(and do still process other datasets)",
        )
        parser.add_argument(
            '-y', '--year',
            default=settings.REVIEW_PROGRAM_YEAR,
            type=int,
            help=f"Program year (default: {settings.REVIEW_PROGRAM_YEAR})",
        )
        parser.add_argument(
            'subcommand',
            choices=('execute', 'inspect',),
            default='execute',
            nargs='?',
            help="either execute command, or inspect state of system only, do "
                 "not load applications (default: execute)",
        )

    def query(self, cursor, expression):
        cursor.execute(expression)
        return cursor

    def write_table(self, *args, **kwargs):
        table = AsciiTable(*args, **kwargs)
        self.stdout.write(table.table)

    def handle(self, entity_id_field, suffix, closed, year, subcommand, invite_only, email_ignore, dry_run, **_options):
        self.survey_1_table_name = 'survey_application_1' + suffix
        self.survey_2_table_name = 'survey_application_2' + suffix
        self.recommendation_table_name = 'survey_recommendation' + suffix
        self.reviewer_table_name = 'survey_reviewer' + suffix
        self.fields_2_table_name = 'survey_application_2_fields' + suffix

        if closed and invite_only:
            raise CommandError(
                "incompatible arguments (--closed, --invite-only) "
                "... nothing to do"
            )

        if invite_only and email_ignore:
            raise CommandError("incompatible arguments (--invite-only, --email-ignore)")

        handler = getattr(self, 'command_' + subcommand)
        with connection.cursor() as cursor:
            try:
                with transaction.atomic():
                    handler(cursor, entity_id_field, year, closed, invite_only, email_ignore, dry_run)
                    if dry_run:
                        raise self.DryRunAbort()
            except self.DryRunAbort:
                self.stdout.write('transaction rolled back for dry run')

    def command_inspect(self, cursor, _entity_id_field, _year, _closed, _invite_only, _email_ignore, _dry_run):
        self.write_table(
            [('table', 'raw', 'linked')] +
            [
                (
                    survey_table_name,
                    self.query(
                        cursor,
                        f'select count(1) from "{survey_table_name}"',
                    ).fetchone()[0],
                    models.ApplicationPage.objects.filter(
                        table_name=survey_table_name,
                    ).count(),
                )
                for survey_table_name in (
                    self.survey_1_table_name,
                    self.survey_2_table_name,
                )
            ],
            'applications loaded',
        )

        self.write_table(
            [
                ('table', 'raw', 'linked'),
                (
                    self.recommendation_table_name,
                    self.query(
                        cursor,
                        f'select count(1) from "{self.recommendation_table_name}"',
                    ).fetchone()[0],
                    models.Reference.objects.filter(
                        table_name=self.recommendation_table_name,
                    ).count(),
                )
            ],
            'recommendations loaded',
        )

    def command_execute(self, cursor, entity_id_field, year, closed, invite_only, email_ignore, dry_run):
        # load field names
        # NOTE: There are 3 "Email" columns in the "first" (second?) survey;
        # NOTE: though, the field IDs appear to overlap across surveys, and
        # NOTE: there's only one in the "second" (first?). So, at least for
        # NOTE: now, we'll assume that's the applicant email field, in
        # NOTE: *all* tables.
        cursor.execute(f"""
            select field_id from {self.fields_2_table_name}
            where field_title ilike 'email'
        """)
        ((applicant_email_field,),) = cursor

        # load application pages
        page_processed = page_created = 0
        survey_table_names = () if (closed or invite_only) else (
            self.survey_1_table_name,
            self.survey_2_table_name,
        )
        for survey_table_name in survey_table_names:
            survey_signature = {
                'table_name': survey_table_name,
                'column_name': entity_id_field,
            }
            cursor.execute(f'''
                select "{entity_id_field}", "{applicant_email_field}"
                from "{survey_table_name}"
            ''')
            for (page_processed, (entity_id, applicant_email)) in enumerate(cursor, page_processed + 1):
                page_signature = dict(survey_signature, entity_code=entity_id)
                with transaction.atomic():
                    (applicant, _created) = models.Applicant.objects.get_or_create(email=applicant_email)
                    if not models.ApplicationPage.objects.filter(**page_signature).exists():
                        (application, _created) = applicant.applications.get_or_create(program_year=year)
                        application.applicationpage_set.create(**page_signature)
                        page_created += 1

        # load recommendation(s)
        recommendation_processed = recommendation_created = 0
        recommendation_signature = {
            'table_name': self.recommendation_table_name,
            'column_name': entity_id_field,
        }
        if invite_only:
            recommendation_rows = ()
        else:
            cursor.execute(f'''
                select "{entity_id_field}", "{applicant_email_field}"
                from "{self.recommendation_table_name}"
            ''')
            recommendation_rows = cursor
        for (recommendation_processed, (entity_id, applicant_email)) in enumerate(cursor, recommendation_processed + 1):
            entity_signature = dict(recommendation_signature, entity_code=entity_id)
            with transaction.atomic():
                (applicant, _created) = models.Applicant.objects.get_or_create(email=applicant_email)
                if not models.Reference.objects.filter(**entity_signature).exists():
                    (application, _created) = applicant.applications.get_or_create(program_year=year)
                    application.reference_set.create(**entity_signature)
                    recommendation_created += 1

        # load reviewer concessions
        concessions_processed = concessions_created = 0

        if closed or invite_only:
            # FIXME: static field IDs
            cursor.execute(f'''\
                select "Field3" email, (
                    case when "Field7" is null then false else true end
                ) is_reviewer, (
                    case when "Field8" is null then false else true end
                ) is_interviewer
                from "{self.reviewer_table_name}"
            ''')
            reviewer_rows = cursor
        else:
            reviewer_rows = ()

        invitation_emails = []

        for (concessions_processed, reviewer_data) in enumerate(reviewer_rows, concessions_processed + 1):
            reviewer_election = {
                col.name: value
                for (col, value) in zip(cursor.description, reviewer_data)
            }
            reviewer_email = reviewer_election.pop('email')

            if invite_only and reviewer_email.lower() not in invite_only:
                continue

            with transaction.atomic():
                # FIXME: interview emails require interviewer name (and add'l information),
                # FIXME: which could be collected/updated here....
                try:
                    email_address = EmailAddress.objects.get(email__iexact=reviewer_email)
                except EmailAddress.MultipleObjectsReturned:
                    self.stderr.write(f'multiple records for {reviewer_email}')
                    continue
                except EmailAddress.DoesNotExist:
                    reviewer = models.Reviewer.objects.create_reviewer(reviewer_email, None)
                    EmailAddress.objects.create(
                        user=reviewer,
                        email=reviewer_email,
                    )
                else:
                    reviewer = email_address.user

                (concession, created) = models.ReviewerConcession.objects.get_or_create(
                    program_year=year,
                    reviewer=reviewer,
                    defaults=reviewer_election,
                )

            if created:
                if concession.is_reviewer or concession.is_interviewer:
                    if not email_ignore or reviewer_email.lower() not in email_ignore:
                        invitation_emails.append(reviewer_email)

                concessions_created += 1

        self.write_table([
            ('entity', 'processed', 'written'),
            ('application pages', page_processed, page_created),
            ('recommendations', recommendation_processed, recommendation_created),
            ('reviewer concessions', concessions_processed, concessions_created),
        ], 'results')

        if dry_run:
            for invitation_email in invitation_emails:
                self.stdout.write(f"WOULD email (dry run): {invitation_email}")
        elif invitation_emails:
            management.call_command('sendinvite', *invitation_emails)
