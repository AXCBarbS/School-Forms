from django.urls import path
from . import manage_views as v

app_name = "manage"
urlpatterns = [
    path("users/", v.users, name="users"),
    path("users/<int:pk>/<str:action>/", v.user_action, name="user_action"),
    path("progress/", v.progress, name="progress"),
    path("audit/", v.audit_log, name="audit"),
    path("import/", v.import_view, name="import"),
]
