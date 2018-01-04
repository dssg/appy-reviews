from django.conf import settings
from django.db.models import Count

from review import models


def apps_to_review(reviewer):
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
    ).order_by(
        'review_count',
    )
