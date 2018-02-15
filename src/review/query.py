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


def apps_to_review(reviewer, *, application_id=None, limit=None,
                   include_reviewed=False, ordered=True):
    """Construct a query set of Applications available to the Reviewer
    to review.

    By default, an ordered RawQuerySet is returned. Set `ordered=False`
    to construct a typical QuerySet without special ordering.

    """
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
            if reviewer.email not in settings.REVIEW_WHITELIST:
                raise UnexpectedReviewer
        else:
            assert result

    # Return stream of applications appropriate to reviewer,
    # optionally ordered by appropriateness

    if not ordered:
        # This is the QuerySet we want, using Django's ORM:
        applications = models.Application.objects.annotate(
            # extend query with these for filtering/ordering
            page_count=Count('applicationpage', distinct=True),
        ).filter(
            # only consider applications ...
            # ... for this program year
            program_year=settings.REVIEW_PROGRAM_YEAR,
            # ... which the applicant completed
            page_count=settings.REVIEW_SURVEY_LENGTH,
            # ... which we haven't culled
            review_decision=True,
        )

        if application_id:
            applications = applications.filter(application_id=application_id)

        if not include_reviewed:
            applications = applications.exclude(
                # exclude applications which this reviewer has already reviewed
                review__reviewer=reviewer,
            )

        if limit is not None:
            applications = applications[:limit]

        return applications

    # However, it's an ORM ...
    # ... and it has at least this bug:
    #   https://code.djangoproject.com/ticket/26390
    #   https://github.com/django/django/pull/6322
    #
    # We'll probably want/need to construct our raw query anyway;
    # so, we'll start with a variation of the *correct* compilation of
    # the above, and try not to make this interface *too* painful for
    # the consuming side of the app, (due to the limitations outside of
    # the Django standard QuerySet).
    #
    # For starters, while we intend here to define the complete set of
    # applications available to the reviewer, consumers now receiving a
    # RawQuerySet are unable to further refine this set for their
    # purposes, (from within the database, rather than in Python); so,
    # we'll accept and interpolate their refinements here.
    limit_expr = '' if limit is None else 'LIMIT %(limit)s'

    reviewed_where_expr = '' if include_reviewed else '''AND
        -- which this reviewer hasn't already reviewed:
        NOT EXISTS (
            SELECT 1 FROM "review" R1
            WHERE R1."application_id" = "application"."application_id" AND
                    R1."reviewer_id" = %(reviewer_id)s
        )'''

    extra_where_expr = '' if application_id is None else '''AND
        "application"."application_id" = %(application_id)s'''

    return models.Application.objects.raw(
        f'''\
            SELECT "application".*
            FROM "application"

            LEFT OUTER JOIN "application_page" USING ("application_id")
            LEFT OUTER JOIN "review" USING ("application_id")
            LEFT OUTER JOIN "review" "positive_review" ON (
                "application"."application_id" = "positive_review"."application_id" AND
                "positive_review"."overall_recommendation" = '{models.Review.OverallRecommendation.interview.name}'
            )
            LEFT OUTER JOIN "review" "unknown_review" ON (
                "application"."application_id" = "unknown_review"."application_id" AND
                "unknown_review"."overall_recommendation" = '{models.Review.OverallRecommendation.only_if.name}'
            )
            LEFT OUTER JOIN "review" "negative_review" ON (
                "application"."application_id" = "negative_review"."application_id" AND
                "negative_review"."overall_recommendation" = '{models.Review.OverallRecommendation.reject.name}'
            )

            -- only consider applications ...
            WHERE
                -- ... which we haven't culled:
                "application"."review_decision" IS TRUE AND
                -- ... for this program year:
                "application"."program_year" = %(program_year)s {reviewed_where_expr} {extra_where_expr}

            -- ... and which the applicant completed:
            GROUP BY "application"."application_id"
            HAVING COUNT(DISTINCT "application_page"."application_page_id") = %(page_count)s

            ORDER BY
                -- prioritize applications by their lack of reviews:
                COUNT(DISTINCT "review"."review_id") ASC,

                -- ... then by the uncertainty of their reviews:
                COUNT(DISTINCT "unknown_review"."review_id") DESC,

                -- ... then by the positivity of their reviews:
                COUNT(DISTINCT "positive_review"."review_id") DESC,

                -- ... and then by the lack of negativity of their reviews:
                COUNT(DISTINCT "negative_review"."review_id") ASC,

                -- ... but otherwise *randomize* applications to ensure
                -- simultaneous reviewers do not review the same application:
                RANDOM()

            {limit_expr}
        ''',
        {
            'page_count': settings.REVIEW_SURVEY_LENGTH,
            'program_year': settings.REVIEW_PROGRAM_YEAR,
            'reviewer_id': reviewer.reviewer_id,
            'application_id': application_id,
            'limit': limit,
        }
    )
