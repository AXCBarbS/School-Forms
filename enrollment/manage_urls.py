from django.urls import path
from . import manage_views as v

app_name = "manage"

urlpatterns = [
    path("users/", v.users, name="users"),
    path("users/<int:pk>/<str:action>/", v.user_action, name="user_action"),
    path("progress/", v.progress, name="progress"),
    path("audit/", v.audit_log, name="audit"),
    path("import/", v.import_view, name="import"),
    path(
        "password-reset-requests/",
        v.password_reset_requests,
        name="password_reset_requests",
    ),
    path(
        "password-reset-requests/<int:pk>/<str:action>/",
        v.password_reset_request_action,
        name="password_reset_request_action",
    ),
]
