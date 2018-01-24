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
            default='',
            help="Suffix to apply to the names of survey tables from which command should read. "
                 "E.g.: If the first page of application survey data has been loaded into "
                 "table \"survey_application_1_2018\", then specify \"_2018\".",
        )
        parser.add_argument(
            '--entity-id', '--id',
            default='EntryId',
            dest='entity_id_field',
            help="Survey data column which should be used as an entity identifier and reference."
                 "(Entities are correlated by email regardless.)",
        )
        # FIXME: year should perhaps come from survey data
        parser.add_argument(
            'year',
            type=int,
            help="Program year",
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

    def handle(self, entity_id_field, suffix, year, subcommand, dry_run, **_options):
        self.survey_1_table_name = 'survey_application_1' + suffix
        self.survey_2_table_name = 'survey_application_2' + suffix
        self.recommendation_table_name = 'survey_recommendation' + suffix
        self.fields_2_table_name = 'survey_application_2_fields' + suffix

        handler = getattr(self, 'command_' + subcommand)
        with connection.cursor() as cursor:
            try:
                with transaction.atomic():
                    handler(cursor, entity_id_field, year)
                    if dry_run:
                        raise DryRunAbort()
            except DryRunAbort:
                self.stdout.write('transaction rolled back for dry run')

    def command_inspect(self, cursor, _entity_id_field, _year):
        self.write_table(
            [('table', 'raw', 'linked')] +
            [
                (
                    survey_table_name,
                    self.query(cursor, f'''\
                        select count(1) from "{survey_table_name}"'''
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
                    self.query(cursor, f'''\
                        select count(1) from "{self.recommendation_table_name}"'''
                    ).fetchone()[0],
                    models.Reference.objects.filter(
                        table_name=self.recommendation_table_name,
                    ).count(),
                )
            ],
            'recommendations loaded',
        )

    def command_execute(self, cursor, entity_id_field, year):
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
        for survey_table_name in (
            self.survey_1_table_name,
            self.survey_2_table_name,
        ):
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

        self.write_table([
            ('entity', 'processed', 'written'),
            ('application pages', page_processed, page_created),
            ('recommendations', recommendation_processed, recommendation_created),
        ], 'results')
