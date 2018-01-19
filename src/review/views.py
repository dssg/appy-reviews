from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.forms import ModelForm
from django.template.response import TemplateResponse

from review import models, query


class ReviewForm(ModelForm):

    class Meta:
        model = models.Review
        fields = (
            'would_interview',
            'interview_suggestions',
            'comments',
        )


@login_required
def review(request):
    try:
        application = query.apps_to_review(request.user)[0]
    except IndexError:
        return TemplateResponse(request, 'review/noapps.html', {
            'program_year': settings.REVIEW_PROGRAM_YEAR,
        })
    except query.UnexpectedReviewer:
        return TemplateResponse(request, 'review/unexpected-reviewer.html', {
            'program_year': settings.REVIEW_PROGRAM_YEAR,
        })
    else:
        return TemplateResponse(request, 'review/review.html', {
            'application': application,
            'review_form': ReviewForm()
        })


# TODO: SES for email verification?
