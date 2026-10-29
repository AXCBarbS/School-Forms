from django.urls import path
from . import views

app_name = "enrollment"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("export/", views.export_xlsx, name="export"),
    path("schools/<str:school_id>/", views.school_entry, name="entry"),
    path("schools/<str:school_id>/review/", views.school_review, name="review"),
    path("schools/<str:school_id>/submit/", views.school_submit, name="submit"),
    path("schools/<str:school_id>/reopen/", views.school_reopen, name="reopen"),
]