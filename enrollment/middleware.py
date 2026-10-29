
"""Enforce mandatory password changes for temporary-password accounts."""

from django.shortcuts import redirect
from django.urls import Resolver404, resolve


class TemporaryPasswordChangeMiddleware:
    """
    Prevent authenticated users with temporary passwords from accessing
    protected portal pages until they change their password.
    """

    ALLOWED_VIEW_NAMES = {
        "accounts:temporary_password_change",
        "accounts:logout",
        "accounts:login",
        "accounts:register",
        "accounts:password_reset",
        "accounts:password_reset_done",
        "accounts:password_reset_confirm",
        "accounts:password_reset_complete",
        "enrollment.middleware.TemporaryPasswordChangeMiddleware",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
        ):
            try:
                match = resolve(request.path_info)
                view_name = match.view_name
            except Resolver404:
                view_name = None

            if (
                view_name not in self.ALLOWED_VIEW_NAMES
                and not request.path_info.startswith("/static/")
                and not request.path_info.startswith("/media/")
            ):
                return redirect("accounts:temporary_password_change")

        return self.get_response(request)
