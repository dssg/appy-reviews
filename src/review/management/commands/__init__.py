from django.conf import settings


APPLICANT_SURVEY_FIELDS = (
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

REFERENCE_SURVEY_FIELDS = (
    ('ref_first', 'Field675'),
    ('ref_last', 'Field676'),
    ('ref_email', 'Field677'),
)

REFERENCE_FORM_URL = ('https://datascience.wufoo.com/forms/'
                      f'?formname={settings.REVIEW_PROGRAM_YEAR}-dssg-fellow-recommendation-form'
                      '&field461={app_email}')
