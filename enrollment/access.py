"""Server-side authorization. Every view obtains schools/records ONLY through these helpers."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

from organization.models import School


def accessible_schools(user):
    qs = School.objects.filter(is_active=True).select_related("district")
    if user.is_system_admin:
        return qs
    if user.district_id is None:
        return qs.none()
    return qs.filter(district_id=user.district_id)


def get_school_or_404(user, school_id):
    """404 (not 403) for other districts so school IDs cannot be probed."""
    return get_object_or_404(accessible_schools(user), school_id=school_id)


def can_manage_district(user, district_id):
    return user.is_system_admin or (user.is_district_admin and user.district_id == district_id)


def manager_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *a, **kw):
        if not request.user.can_manage_users:
            raise PermissionDenied
        return view(request, *a, **kw)
    return wrapper


def system_admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *a, **kw):
        if not request.user.is_system_admin:
            raise PermissionDenied
        return view(request, *a, **kw)
    return wrapper
