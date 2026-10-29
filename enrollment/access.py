
"""Server-side authorization helpers for schools, records, and management views."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from organization.models import School


def accessible_schools(user):
    qs = School.objects.filter(is_active=True).select_related("district")

    if user.is_system_admin:
        return qs

    if user.district_id is None:
        return qs.none()

    return qs.filter(district_id=user.district_id)


def get_school_or_404(user, school_id):
    """Return 404 for inaccessible schools to prevent ID probing."""
    return get_object_or_404(
        accessible_schools(user),
        school_id=school_id,
    )


def can_manage_district(user, district_id):
    return user.is_system_admin or (
        user.is_district_admin and user.district_id == district_id
    )


def _password_change_redirect(request):
    """
    Redirect authenticated users who must change their temporary password.

    The temporary password-change page and logout remain accessible.
    """
    user = request.user

    if not user.is_authenticated:
        return None

    if not getattr(user, "must_change_password", False):
        return None

    allowed_url_names = {
        "accounts:temporary_password_change",
        "accounts:logout",
    }

    if request.resolver_match and request.resolver_match.view_name in allowed_url_names:
        return None

    return redirect("accounts:temporary_password_change")


def manager_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        password_redirect = _password_change_redirect(request)
        if password_redirect is not None:
            return password_redirect

        if not request.user.can_manage_users:
            raise PermissionDenied

        return view(request, *args, **kwargs)

    return wrapper


def system_admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        password_redirect = _password_change_redirect(request)
        if password_redirect is not None:
            return password_redirect

        if not request.user.is_system_admin:
            raise PermissionDenied

        return view(request, *args, **kwargs)

    return wrapper
