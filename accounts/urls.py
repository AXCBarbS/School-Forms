
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),

    # Email change
    path("email/change/", views.email_change, name="email_change"),
    path(
        "email/change/verify/",
        views.email_change_verify,
        name="email_change_verify",
    ),

    # Password reset request (admin approval required)
    path(
        "password-reset/",
        views.password_reset,
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        views.password_reset_done,
        name="password_reset_done",
    ),

    # Legacy reset links redirect to the request page
    path(
        "reset/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        views.password_reset_complete,
        name="password_reset_complete",
    ),

    # Mandatory change after using a temporary password
    path(
        "password/change-temporary/",
        views.temporary_password_change,
        name="temporary_password_change",
    ),
]
