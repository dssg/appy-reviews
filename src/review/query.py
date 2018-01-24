import enum

from django.conf import settings
from django.db import connection
from django.db.models import Count

from review import models


class SurveyTableName(str, enum.Enum):
    """str-Enum of survey table names"""

    reviewer = 'survey_reviewer_{REVIEW_PROGRAM_YEAR}'
    reviewer_fields = 'survey_reviewer_fields_{REVIEW_PROGRAM_YEAR}'

    def __format__(self, spec):
        return self.__str__().__format__(spec)

    def __str__(self):
        return self.value.format(
            REVIEW_PROGRAM_YEAR=settings.REVIEW_PROGRAM_YEAR,
        )


class UnexpectedReviewer(LookupError):
    pass


def apps_to_review(reviewer):
    # Test that reviewer can help with application reviews
    #
    # (For the moment, simply using data collected from wufoo;
    # perhaps next year we'll gather this upon registration.)
    #
    with connection.cursor() as cursor:
        cursor.execute(f'''\
			select field_id
            from "{SurveyTableName.reviewer_fields}"
			where field_title in %(field_titles)s
            order by field_title
            ''',
            {'field_titles': ('Application Reviews',
                              'Email')},
        )
        (
            (field_id_reviewer,),
            (field_id_email,),
         ) = cursor

        cursor.execute(f'''\
            select 1
            from "{SurveyTableName.reviewer}"
            where "{field_id_email}"=%(reviewer_email)s and
                  "{field_id_reviewer}"!=''
            ''',
            {'reviewer_email': reviewer.email},
        )
        try:
            (result,) = next(iter(cursor))
        except StopIteration:
            raise UnexpectedReviewer
        else:
            assert result

    # Return stream of applications appropriate to reviewer,
    # ordered by appropriateness
    return models.Application.objects.prefetch_related(
        'applicationpage_set',
        'reference_set',
    ).annotate(
        page_count=Count('applicationpage'),
        review_count=Count('review'),
    ).filter(
        decision='',
        program_year=settings.REVIEW_PROGRAM_YEAR,
        page_count=settings.REVIEW_SURVEY_LENGTH,
    ).exclude(
        review__reviewer=reviewer,
    ).order_by(
        'review_count',
    )
