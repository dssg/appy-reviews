from allauth.account.models import EmailAddress
from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from terminaltables import AsciiTable

from review import models


class DryRunAbort(RuntimeError):
    pass


class Command(BaseCommand):

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
                 "no fellow applications will be loaded.",
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

    def handle(self, entity_id_field, suffix, closed, year, subcommand, dry_run, **_options):
        self.survey_1_table_name = 'survey_application_1' + suffix
        self.survey_2_table_name = 'survey_application_2' + suffix
        self.recommendation_table_name = 'survey_recommendation' + suffix
        self.reviewer_table_name = 'survey_reviewer' + suffix
        self.fields_2_table_name = 'survey_application_2_fields' + suffix

        handler = getattr(self, 'command_' + subcommand)
        with connection.cursor() as cursor:
            try:
                with transaction.atomic():
                    handler(cursor, entity_id_field, year, closed)
                    if dry_run:
                        raise DryRunAbort()
            except DryRunAbort:
                self.stdout.write('transaction rolled back for dry run')

    def command_inspect(self, cursor, _entity_id_field, _year, _closed):
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

    def command_execute(self, cursor, entity_id_field, year, closed):
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
        survey_table_names = () if closed else (
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
        cursor.execute(f'''
            select "{entity_id_field}", "{applicant_email_field}"
            from "{self.recommendation_table_name}"
        ''')
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

        # FIXME: static field IDs
        cursor.execute(f'''\
            select "Field3" email, (
                case when "Field7" is null then false else true end
            ) is_reviewer, (
                case when "Field8" is null then false else true end
            ) is_interviewer
            from "{self.reviewer_table_name}"
        ''')
        for (concessions_processed, reviewer_data) in enumerate(cursor, concessions_processed + 1):
            reviewer_election = {
                col.name: value
                for (col, value) in zip(cursor.description, reviewer_data)
            }
            reviewer_email = reviewer_election.pop('email')

            with transaction.atomic():
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
                    management.call_command('sendinvite', reviewer_email)

                concessions_created += 1

        self.write_table([
            ('entity', 'processed', 'written'),
            ('application pages', page_processed, page_created),
            ('recommendations', recommendation_processed, recommendation_created),
            ('reviewer concessions', concessions_processed, concessions_created),
        ], 'results')
