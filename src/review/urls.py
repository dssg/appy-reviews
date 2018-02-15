from django.urls import path, re_path
from django.views.generic import RedirectView

from . import views


urlpatterns = [
    path('', views.index, name='index'),

    path('review/application/', views.review, name='review-application'),
    path('review/application/<int:application_id>/', views.review, name='review-application'),

    # path('review/interview/', views.review, name='review-interview'),
    # path('review/interview/...', views.review, name='review-interview-detail'),

    re_path(r"confirm-email/(?P<key>[-:\w]+)/$",
            views.invite_confirm_email,
            name="account_confirm_email"),

    path('password/set/',
         views.invite_password_set,
         name='account_set_password'),
]
