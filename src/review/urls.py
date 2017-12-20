from django.urls import path
from django.views.generic import RedirectView

from . import views


urlpatterns = [
    path('review/', views.review, name='review'),

    # TODO: do something with index? (dashboard?)
    path('', RedirectView.as_view(pattern_name='review', permanent=False)),
]
