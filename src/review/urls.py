from django.urls import path, re_path

from . import views


urlpatterns = [
    path('', views.index, name='index'),

    path('review/application/', views.review_application, name='review-application'),
    path('review/application/<int:application_id>/', views.review_application, name='review-application'),

    # path('review/interview/', views.review_interview, name='review-interview'),
    path('review/interview/<int:assignment_id>/', views.review_interview, name='review-interview'),

    path('application.json', views.list_applications, {'content_type': 'json'}, name='application-list-json'),
    # path('application/', views.list_applications, name='application-list'),

    path('report/', views.report, name='report'),

    re_path(r"confirm-email/(?P<key>[-:\w]+)/$",
            views.invite_confirm_email,
            name="account_confirm_email"),

    path('password/set/',
         views.invite_password_set,
         name='account_set_password'),
]
