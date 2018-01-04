from django.contrib.auth.decorators import login_required
from django.template.response import TemplateResponse

from review import query


@login_required
def review(request):
    return TemplateResponse(request, 'review/review.html', {
        'application': query.apps_to_review(request.user)[0],
    })


# TODO: SES for email verification?
