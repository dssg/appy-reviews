import functools

from django import forms, http
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods

from review import models, query


class ReviewForm(forms.ModelForm):

    class Meta:
        model = models.Review
        fields = (
            'application',
            'would_interview',
            'interview_suggestions',
            'comments',
        )
        widgets = {
            'application': forms.HiddenInput(),
        }


class RatingForm(forms.ModelForm):

    # rate skill 1 - 5
    score = forms.ChoiceField(
        widget=forms.RadioSelect,
        choices=[(str(value),) * 2 for value in range(1, 6)],
    )

    class Meta:
        model = models.Rating
        fields = (
            'label',
            'score',
        )


class StaticRatingForm(RatingForm):

    def __init__(self, *args, label_text=None, **kwargs):
        super().__init__(*args, **kwargs)

        if label_text is not None:
            self.fields['score'].label = label_text

    class Meta(RatingForm.Meta):
        widgets = {
            'label': forms.HiddenInput(),
        }


class StaticRatingFormSet(forms.BaseFormSet):

    def __init__(self, *args, label_texts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_texts = label_texts

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['label_text'] = self.label_texts and self.label_texts[index]
        return kwargs


def make_rating_formset(*labels,
                        base_form=StaticRatingForm,
                        base_formset=StaticRatingFormSet,
                        **kwargs):
    label_count = len(labels)
    label_field = base_form.base_fields['label']
    label_choices = dict(label_field.choices)

    if label_count == 0:
        return make_rating_formset(
            *(label for label in label_choices if label),
            base_form=base_form,
            base_formset=base_formset,
            **kwargs
        )

    RatingFormSet = forms.formset_factory(
        base_form,
        base_formset,
        min_num=label_count,
        max_num=label_count,
        validate_min=True,
        validate_max=True,
    )
    return RatingFormSet(
        initial=[{'label': label} for label in labels],
        label_texts=[label_choices[label] for label in labels],
        **kwargs
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
        rating_formset = make_rating_formset(data=request.POST)

        # rather than use a breaking operator such as "and" or "or",
        # ensure both are checked...
        try:
            validations = (
                review_form.is_valid(),
                rating_formset.is_valid(),
            )
        except forms.ValidationError:
            return http.HttpResponseBadRequest("Bad request")

        # ...even while invalidity in either invalidate this branch:
        if all(validations):
            with transaction.atomic():
                review = review_form.save(commit=False)
                review.reviewer = request.user
                review.save()
                review_form.save_m2m()

                # ModelFormSet is a bear -- avoiding it for now anyway
                for rating_form in rating_formset.forms:
                    rating = rating_form.save(commit=False)
                    rating.review = review
                    rating.save()
                    rating_form.save_m2m()

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
        rating_formset = make_rating_formset()

    return TemplateResponse(request, 'review/review.html', {
        'application': application,
        'application_fields': settings.REVIEW_APPLICATION_FIELDS,
        'rating_formset': rating_formset,
        'review_form': review_form,
        'review_count': request.user.reviews.filter(
            application__program_year=settings.REVIEW_PROGRAM_YEAR
        ).count(),
    })


# TODO: SES for email verification?
