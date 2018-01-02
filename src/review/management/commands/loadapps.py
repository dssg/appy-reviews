from django.core.management.base import BaseCommand
from django.db import connection, transaction

from review import models


class Command(BaseCommand):

    help = (
        "Map Wufoo application/survey data into the Review Web application. "
        "Requires that Wufoo data has been loaded into the database. (See command: loadwufoo.)"
    )

    def add_arguments(self, parser):
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
        # TODO: Year should perhaps come from survey data
        parser.add_argument(
            '-y', '--year',
            type=int,
            help="Program year",
        )

    def handle(self, entity_id_field, suffix, year, **_options):
        if not year:
            # TODO
            raise Exception(repr(year))
        survey_1_table_name = 'survey_application_1' + suffix
        survey_2_table_name = 'survey_application_2' + suffix
        recommendation_table_name = 'survey_recommendation' + suffix
        fields_2_table_name = 'survey_application_2_fields' + suffix

        with connection.cursor() as cursor:
            # load field names
            # FIXME: Field tables don't appear as useful as anticipated.
            # FIXME: Were they imported incorrectly, or could they be named better
            # FIXME: in Wufoo?
            #
            # FIXME: There are 3 "Email" columns in the "first" (second?) survey;
            # FIXME: though, the field IDs appear to overlap across surveys, and
            # FIXME: there's only one in the "second" (first?). So, at least for
            # FIXME: now, we'll assume that's the applicant email field, in
            # FIXME: *all* tables.
            cursor.execute(f"""
                select field_id from {fields_2_table_name}
                where field_title ilike 'email'
            """)
            ((applicant_email_field,),) = cursor

            # load application pages
            for survey_table_name in (
                survey_1_table_name,
                survey_2_table_name,
            ):
                survey_signature = {
                    'table_name': survey_table_name,
                    'column_name': entity_id_field,
                }
                cursor.execute(f'''
                    select "{entity_id_field}", "{applicant_email_field}"
                    from "{survey_table_name}"
                ''')
                for (entity_id, applicant_email) in cursor:
                    page_signature = dict(survey_signature, entity_code=entity_id)
                    with transaction.atomic():
                        (applicant, _created) = models.Applicant.objects.get_or_create(email=applicant_email)
                        if not models.ApplicationPage.objects.filter(**page_signature).exists():
                            (application, _created) = applicant.applications.get_or_create(program_year=year)
                            application.applicationpage_set.create(**page_signature)

            # load recommendation(s)
            recommendation_signature = {
                'table_name': recommendation_table_name,
                'column_name': entity_id_field,
            }
            cursor.execute(f'''
                select "{entity_id_field}", "{applicant_email_field}"
                from "{recommendation_table_name}"
            ''')
            for (entity_id, applicant_email) in cursor:
                entity_signature = dict(recommendation_signature, entity_code=entity_id)
                with transaction.atomic():
                    (applicant, _created) = models.Applicant.objects.get_or_create(email=applicant_email)
                    if not models.Reference.objects.filter(**entity_signature).exists():
                        (application, _created) = applicant.applications.get_or_create(program_year=year)
                        application.reference_set.create(**entity_signature)
