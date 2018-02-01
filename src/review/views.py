import functools
import urllib

import allauth.account.views
import allauth.account.utils
from allauth.compat import is_anonymous
from allauth.utils import get_request_param
from django import forms, http
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from review import models, query


RATING_FIELDS = tuple(models.Review.rating_fields())


class RatingWidget(forms.RadioSelect):

    rating_choices = (
        (0, 'Indeterminate'),
        (-1, 'Inadequate'),
        (1, 'Adequate'),
        (2, 'Exceptional'),
    )
    is_rating = True

    def __init__(self, attrs=None, choices=rating_choices):
        super().__init__(attrs, choices)


class ReviewForm(forms.ModelForm):

    # ensure empty option isn't provided
    # (ModelForm insists on inserting it)
    overall_recommendation = forms.ChoiceField(
        widget=forms.RadioSelect,
        choices=list(models.Review.OverallRecommendation.__members__.items()),
    )

    class Meta:
        model = models.Review
        fields = (
            'application',
        ) + RATING_FIELDS + (
            'overall_recommendation',
            'comments',
            'interview_suggestions',
            'would_interview',
        )
        widgets = dict(
            (
                (rating_field, RatingWidget)
                for rating_field in RATING_FIELDS
            ),
            application=forms.HiddenInput,
        )


def unexpected_review(handler):
    def wrapped(request, *args, **kwargs):
        try:
            return handler(request, *args, **kwargs)
        except query.UnexpectedReviewer:
            return TemplateResponse(request, 'review/unexpected-reviewer.html', {
                'program_year': settings.REVIEW_PROGRAM_YEAR,
            })

    return functools.wraps(handler)(wrapped)


@require_http_methods(['GET', 'POST'])
@login_required
@unexpected_review
def review(request):
    if request.method == 'POST':
        application_id = request.POST.get('application', '')

        if not application_id.isdigit():
            return http.HttpResponseBadRequest("Bad request")

        applications = query.apps_to_review(request.user)

        try:
            application = applications.get(application_id=application_id)
        except models.Application.DoesNotExist:
            # application *may* exist but it is not in the set of those
            # allowed to reviewer
            return http.HttpResponseForbidden("Forbidden")

        review_form = ReviewForm(data=request.POST)
        if review_form.is_valid():
            with transaction.atomic():
                review = review_form.save(commit=False)
                review.reviewer = request.user
                review.save()
                review_form.save_m2m()

            messages.success(request, 'Review submitted')
            return redirect('review-application')
    else:
        try:
            application = query.apps_to_review(request.user)[0]
        except IndexError:
            return TemplateResponse(request, 'review/noapps.html', {
                'program_year': settings.REVIEW_PROGRAM_YEAR,
                'review_count': request.user.reviews.filter(
                    application__program_year=settings.REVIEW_PROGRAM_YEAR
                ).count(),
            })

        review_form = ReviewForm(initial={'application': application})

    return TemplateResponse(request, 'review/review.html', {
        'application': application,
        'application_fields': settings.REVIEW_APPLICATION_FIELDS,
        'review_form': review_form,
        'review_count': request.user.reviews.filter(
            application__program_year=settings.REVIEW_PROGRAM_YEAR
        ).count(),
    })


class InvitationalConfirmEmailView(allauth.account.views.ConfirmEmailView):

    def get_invitation_redirect_url(self):
        return (
            reverse('account_set_password') +
            '?' + urllib.parse.urlencode([
                (InvitationalPasswordSetView.redirect_field_name, self.get_redirect_url()),
            ])
        )

    def login_on_confirm(self, confirmation):
        """Override default to:

            * *disable* check, via session, that user *just* requested
            this email confirmation (*we* intend to send these
            confirmation emails)

            * redirect user, post login, to set their password, iff
            their password is "unusable" (unset) and they don't have
            access through a socialaccount

        """
        user = confirmation.email_address.user
        if is_anonymous(self.request.user):
            if user.has_usable_password() or user.socialaccount_set.exists():
                # passed as callable, as this method
                # depends on the authenticated state
                redirect_url = self.get_redirect_url
            else:
                redirect_url = self.get_invitation_redirect_url

            return allauth.account.utils.perform_login(
                self.request,
                user,
                allauth.account.app_settings.EmailVerificationMethod.NONE,
                redirect_url=redirect_url,
            )

        return None

invite_confirm_email = InvitationalConfirmEmailView.as_view()


class InvitationalPasswordSetView(allauth.account.views.PasswordSetView):

    redirect_field_name = 'next'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        redirect_field_value = get_request_param(self.request,
                                                 self.redirect_field_name)
        ctx.update(
            redirect_field_name=self.redirect_field_name,
            redirect_field_value=redirect_field_value,
        )
        return ctx

    def get_success_url(self):
        return allauth.account.utils.get_next_redirect_url(
            self.request,
            self.redirect_field_name,
        ) or super().get_success_url()

invite_password_set = login_required(InvitationalPasswordSetView.as_view())
