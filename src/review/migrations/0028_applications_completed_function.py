from django.db import migrations


SQL_FN_NAME = 'applications_completed'


class Migration(migrations.Migration):

    dependencies = [
        ('review', '0027_applicationcompletemessage'),
    ]

    operations = [
        migrations.RunSQL(
            f"""CREATE OR REPLACE FUNCTION {SQL_FN_NAME}(int) RETURNS SETOF application AS $$
                SELECT application.* FROM application JOIN application_page USING (application_id)
                WHERE application.program_year = $1 AND
                      application.review_decision IS TRUE AND
                      application.withdrawn IS NULL
                GROUP BY (application_id)
                HAVING COUNT(DISTINCT application_page.application_page_id) > 1;
              $$ LANGUAGE SQL;
            """,
            f"""DROP FUNCTION IF EXISTS {SQL_FN_NAME}""",
        ),
    ]
