import collections
import itertools

import django_tables2 as tables
from django.conf import settings
from django.db.models import Count, Q, Max

from review import models, query


def histogram(stream):
    counts = collections.defaultdict(int)
    for item in stream:
        counts[item] += 1
    return counts


class SummingColumn(tables.Column):

    def render_footer(self, bound_column, table):
        return sum(bound_column.accessor.resolve(row) for row in table.data)


class TitledMixin:

    __title__ = None

    @classmethod
    def title(cls):
        return cls.__title__


class TotalingTable(TitledMixin, tables.Table):

    total = tables.Column(footer='Total', default='', orderable=False, verbose_name='')


# Application review report #

def application_review_counts():
    apps = query.unordered_reviewable_apps()
    return apps.annotate(
        review_count=Count('application_reviews', distinct=True),
    ).values_list('review_count', flat=True)


def application_review_histogram():
    return histogram(application_review_counts().iterator())


class ApplicationReviewTable(TotalingTable):

    __title__ = 'Application reviews'

    review_count = tables.Column(
        verbose_name='Reviews submitted',
        footer=lambda table: sum(row['review_count'] * row['app_count'] for row in table.data)
    )
    app_count = SummingColumn(verbose_name='Applications')


def application_review_table(**kwargs):
    return ApplicationReviewTable(
        (
            {
                'review_count': review_count,
                'app_count': app_count,
            }
            for (review_count, app_count) in sorted(
                application_review_histogram().items(),
                reverse=True,
            )
        ),
        **kwargs
    )


# Application recommendation report #

APPLICATION_RECOMMENDATION_VALUES = (
    'interview1_decision',
    'interview_count',
    'maybe_interview_count',
    'reject_count',
    'only_if_count',
)


def application_recommendation_counts():
    apps = query.unordered_reviewable_apps()
    return apps.annotate(
        interview_count=Count(
            'application_reviews',
            distinct=True,
            filter=Q(
                application_reviews__overall_recommendation='interview',
            ),
        ),
        maybe_interview_count=Count(
            'application_reviews',
            distinct=True,
            filter=Q(
                application_reviews__overall_recommendation='maybe_interview',
            ),
        ),
        only_if_count=Count(
            'application_reviews',
            distinct=True,
            filter=Q(
                application_reviews__overall_recommendation='only_if',
            ),
        ),
        reject_count=Count(
            'application_reviews',
            distinct=True,
            filter=Q(
                application_reviews__overall_recommendation='reject',
            ),
        ),
    ).values_list(*APPLICATION_RECOMMENDATION_VALUES).order_by(
        '-interview1_decision',
        '-interview_count', '-maybe_interview_count', '-reject_count')


def application_recommendation_histogram():
    return histogram(application_recommendation_counts().iterator())


class ApplicationRecommendationTable(TotalingTable):

    __title__ = 'Application recommendations'

    # TODO: review whether this stat is desired here
    interview1_decision = tables.Column(verbose_name='Decision: interview')

    interview_count = tables.Column(verbose_name='Review: interview')
    maybe_interview_count = tables.Column(verbose_name='Review: maybe')
    reject_count = tables.Column(verbose_name='Review: reject')
    only_if_count = tables.Column(verbose_name='Review: only if…')
    app_count = SummingColumn(verbose_name='Applications')


def application_recommendation_table(**kwargs):
    return ApplicationRecommendationTable(
        (
            dict(
                itertools.chain(
                    zip(APPLICATION_RECOMMENDATION_VALUES, group_key),
                    [('app_count', group_count)]
                )
            )
            for (group_key, group_count) in application_recommendation_histogram().items()
        ),
        **kwargs,
    )


# Reviewer reviews report #

def reviewer_review_counts():
    current_year_filter = Q(
        application_reviews__application__program_year=settings.REVIEW_PROGRAM_YEAR,
    )

    return (
        models.Reviewer.objects
        .annotate(
            last_review=Max(
                'application_reviews__submitted',
                filter=current_year_filter,
            ),
            review_count=Count(
                'application_reviews',
                filter=current_year_filter,
            ),
            interview_count=Count(
                'application_reviews',
                filter=(
                    current_year_filter &
                    Q(application_reviews__overall_recommendation='interview')
                ),
            ),
            maybe_interview_count=Count(
                'application_reviews',
                filter=(
                    current_year_filter &
                    Q(application_reviews__overall_recommendation='maybe_interview')
                ),
            ),
            only_if_count=Count(
                'application_reviews',
                filter=(
                    current_year_filter &
                    Q(application_reviews__overall_recommendation='only_if')
                ),
            ),
            reject_count=Count(
                'application_reviews',
                filter=(
                    current_year_filter &
                    Q(application_reviews__overall_recommendation='reject')
                ),
            ),
        )
        .filter(
            Q(review_count__gt=0) |
            Q(
                concessions__is_reviewer=True,
                concessions__program_year=settings.REVIEW_PROGRAM_YEAR,
            )
        )
        .values('email', 'last_review', 'review_count', 'interview_count',
                'maybe_interview_count', 'only_if_count', 'reject_count')
        .order_by('-review_count', 'email')
    )


class ReviewerReviewTable(TotalingTable):

    __title__ = 'Reviewer reviews'

    email = tables.Column()
    review_count = SummingColumn(verbose_name='Reviews submitted')
    interview_count = SummingColumn('Review: interview')
    maybe_interview_count = SummingColumn('Review: maybe')
    only_if_count = SummingColumn('Review: only if…')
    reject_count = SummingColumn('Review: reject')
    last_review = tables.Column()


def reviewer_review_table(**kwargs):
    return ReviewerReviewTable(reviewer_review_counts().iterator(), **kwargs)
