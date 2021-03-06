import functools
import itertools
import urllib

import allauth.account.views
import allauth.account.utils
from allauth.utils import get_request_param
from django import forms, http
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.shortcuts import redirect, get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
from django_tables2 import RequestConfig

from review import models, query, reports


RATING_FIELDS = models.ApplicationReview.rating_fields()
RATING_NAMES = tuple(RATING_FIELDS)

INTERVIEW_QUESTION_FIELDS = models.InterviewReview.question_fields()
INTERVIEW_QUESTION_NAMES = tuple(INTERVIEW_QUESTION_FIELDS)


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

    group_single = True

    # ensure empty option isn't provided
    # (ModelForm insists on inserting it)
    overall_recommendation = forms.ChoiceField(widget=forms.RadioSelect)

    def __init__(self, *args, reviewer, **kwargs):
        super().__init__(*args, **kwargs)
        self.reviewer = reviewer

        if self.reviewer.trusted:
            for field_name in RATING_NAMES:
                self.fields[field_name].required = False

        self.fields['overall_recommendation'].choices = [
            (name, str(label)) for (name, label)
            in self._meta.model.OverallRecommendation.__members__.items()
        ]

    def visible_field_groups(self):
        visible_fields = self.visible_fields()

        try:
            field_group_texts = self._meta.model.field_group_texts
        except AttributeError:
            return [(None, visible_fields)]

        field_group_stream = itertools.groupby(visible_fields,
                                               lambda field: field_group_texts[field.name])

        # cannot return exhaustible generators to templates, so construct lists
        field_groups = [
            (group_text, list(field_group))
            for (group_text, field_group) in field_group_stream
        ]

        if self.group_single or len(field_groups) > 1:
            return field_groups

        ((_group_text, field_group),) = field_groups
        return [(None, field_group)]


class ApplicationReviewForm(ReviewForm):

    class Meta:
        model = models.ApplicationReview
        fields = (
            'application',
        ) + RATING_NAMES + (
            'overall_recommendation',
            'comments',
            'interview_suggestions',
            'would_interview',
        )
        widgets = dict(
            (
                (rating_field, RatingWidget)
                for rating_field in RATING_NAMES
            ),
            application=forms.HiddenInput,
        )

    def full_clean(self):
        super().full_clean()

        if not self.errors:
            self.instance.reviewer = self.reviewer


class InterviewReviewOneForm(ReviewForm):

    class Meta:
        model = models.InterviewReview
        fields = INTERVIEW_QUESTION_NAMES + RATING_NAMES + (
            'overall_recommendation',
            'comments',
            'candidate_rank',
        )
        widgets = {rating_field: RatingWidget for rating_field in RATING_NAMES}


class InterviewReviewPlusForm(ReviewForm):

    group_single = False

    class Meta:
        model = models.InterviewReview
        fields = RATING_NAMES + (
            'overall_recommendation',
            'comments',
            'candidate_rank',
        )
        widgets = {rating_field: RatingWidget for rating_field in RATING_NAMES}


def unexpected_review(handler):
    def wrapped(request, *args, **kwargs):
        try:
            return handler(request, *args, **kwargs)
        except query.UnexpectedReviewer:
            return TemplateResponse(request, 'review/unexpected-reviewer.html', {
                'program_year': settings.REVIEW_PROGRAM_YEAR,
            })

    return functools.wraps(handler)(wrapped)


@require_GET
@login_required
def index(request):
    reviews = request.user.application_reviews.current_year()
    interviews = request.user.interview_assignments.current_year()

    return TemplateResponse(request, 'review/index.html', {
        'interviews': interviews,
        'reviews': reviews,
        'review_count': len(reviews),  # let's get them!
        'program_year': settings.REVIEW_PROGRAM_YEAR,
    })


@require_GET
@login_required
@unexpected_review
def list_applications(request, content_type='html'):
    if content_type != 'json':
        raise NotImplementedError

    query_raw = request.GET.get('q', '')
    applications = query.apps_to_review(request.user,
                                        include_reviewed=True,
                                        ordered=False)

    if query_raw:
        with connection.cursor() as cursor:
            # FIXME: assumes survey field IDs
            #
            # These could -- and perhaps simply should -- be configured in settings.
            #
            # Alternatively, (though not *great*), could look these up, assuming applicant's
            # are the first listed:
            #
            #     select field_id from (
            #         select distinct on (2) field_id, lower(field_title)
            #         from survey_application_1_fields_YEAR
            #         where field_id like 'Field%' and (
            #             field_title ilike 'first%' or
            #             field_title ilike 'last%' or
            #             field_title ilike 'email%'
            #         ) order by 2, field_id
            #     ) _fields
            #     order by field_id
            #     limit 3
            #
            cursor.execute(
                f'''\
                    SELECT "EntryId"
                    FROM "survey_application_1_{settings.REVIEW_PROGRAM_YEAR}"
                    WHERE
                        LOWER("Field451") IN %(query_terms)s OR
                        LOWER("Field452") IN %(query_terms)s OR
                        LOWER("Field461") IN %(query_terms)s
                ''',
                {'query_terms': tuple(query_raw.lower().split())}
            )
            entry_ids = [row[0] for row in cursor]

        applications = applications.filter(
            applicationpage__table_name=f'survey_application_1_{settings.REVIEW_PROGRAM_YEAR}',
            applicationpage__column_name='EntryId',
            applicationpage__entity_code__in=entry_ids,
        )
    elif not request.user.trusted:
        return http.JsonResponse(
            {
                'status': 'forbidden',
                'error': 'not allowed',
            },
            status=403,
        )

    return http.JsonResponse({
        'status': 'ok',
        'results': list(
            applications
            .values(
                'application_id',
                'applicant_id',
                'program_year',
                'created',
                'applicant__email',
            )
            .order_by(
                'applicant__email',
            )
        ),
    })


@require_http_methods(['GET', 'POST'])
@login_required
@unexpected_review
def review_application(request, application_id=None):
    if application_id:
        applications = query.apps_to_review(request.user,
                                            application_id=application_id,
                                            include_reviewed=True)
        try:
            (application,) = applications
        except ValueError:
            return http.HttpResponseNotFound("Could not find application to review")

        try:
            review = application.application_reviews.get(reviewer=request.user)
        except models.ApplicationReview.DoesNotExist:
            review = None
    else:
        review = None

    if request.method == 'POST':
        if application_id is None:
            application_id = request.POST.get('application', '')

            if not application_id.isdigit():
                return http.HttpResponseBadRequest("Bad request")

            applications = query.apps_to_review(request.user,
                                                application_id=application_id)

            try:
                (application,) = applications
            except ValueError:
                # application *may* exist but it is not in the set of those
                # allowed to reviewer
                return http.HttpResponseForbidden("Forbidden")
        elif request.POST.get('application') != str(application_id):
            return http.HttpResponseBadRequest("Bad request")

        review_form = ApplicationReviewForm(data=request.POST,
                                            instance=review,
                                            reviewer=request.user)
        if review_form.is_valid():
            with transaction.atomic():
                review_form.save()

            messages.success(request, 'Review submitted')
            return redirect(request.path)
    else:
        if application_id is None:
            applications = query.apps_to_review(request.user, limit=1)

            try:
                (application,) = applications
            except ValueError:
                return TemplateResponse(request, 'review/noapps.html', {
                    'program_year': settings.REVIEW_PROGRAM_YEAR,
                    'review_count': request.user.application_reviews.current_year().count(),
                })

        review_form = ApplicationReviewForm(
            instance=review,
            initial={'application': application},
            reviewer=request.user,
        )

    return TemplateResponse(request, 'review/review.html', {
        'application': application,
        'application_fields': settings.REVIEW_APPLICATION_FIELDS,
        'review_form': review_form,
        'review_count': request.user.application_reviews.current_year().count(),
        'review_type': 'application',
    })


@require_http_methods(['GET', 'POST'])
@login_required
def review_interview(request, assignment_id):
    assignment = get_object_or_404(models.InterviewAssignment, pk=assignment_id)
    if assignment.reviewer != request.user:
        return http.HttpResponseForbidden("Forbidden")

    try:
        review = assignment.interview_review
    except models.InterviewReview.DoesNotExist:
        review = models.InterviewReview(interview_assignment=assignment)

    if assignment.interview_round > assignment.InterviewRound.round_one:
        make_form = InterviewReviewPlusForm
    else:
        make_form = InterviewReviewOneForm

    if request.method == 'POST':
        review_form = make_form(data=request.POST,
                                instance=review,
                                reviewer=request.user)
        if review_form.is_valid():
            with transaction.atomic():
                review_form.save()

            messages.success(request, 'Review submitted')
            return redirect('index')
    else:
        review_form = make_form(instance=review, reviewer=request.user)

    interview_reviews = models.InterviewReview.objects.filter(
        interview_assignment__application=assignment.application,
        interview_assignment__interview_round__lt=assignment.interview_round,
    ).exclude(
        interview_assignment=assignment,
    )

    return TemplateResponse(request, 'review/review.html', {
        'application': assignment.application,
        'application_fields': settings.REVIEW_APPLICATION_FIELDS,
        'review_form': review_form,
        'review_type': 'interview',
        'application_reviews': assignment.application.application_reviews.all(),
        'interview_reviews': interview_reviews,
        'rating_fields': RATING_FIELDS,
        'interview_fields': INTERVIEW_QUESTION_FIELDS,
    })


REPORT_TABLES = (
    ('app_review', reports.application_review_table),
    ('app_recommendation', reports.application_recommendation_table),
    ('reviewer_review', reports.reviewer_review_table),
)


@require_GET
@login_required
def report(request):
    if not request.user.trusted:
        return http.HttpResponseForbidden("Forbidden")

    report_tables = [
        report_getter(prefix=f'{report_key}_')
        for (report_key, report_getter) in REPORT_TABLES
    ]
    table_config = RequestConfig(request)
    for report_table in report_tables:
        table_config.configure(report_table)

    return TemplateResponse(request, 'review/report.html', {
        'program_year': settings.REVIEW_PROGRAM_YEAR,
        'reports': report_tables,
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
        if self.request.user.is_anonymous:
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
