from django.urls import path
from django.views.generic import RedirectView

from . import views


urlpatterns = [
    path('review/application/', views.review, name='review-application'),
    # path('review/interview/', views.review, name='review-interview'),
    # path('review/interview/...', views.review, name='review-interview-detail'),

    # TODO: do something with index? (dashboard?)
    path('', RedirectView.as_view(pattern_name='review-application', permanent=False)),
]
