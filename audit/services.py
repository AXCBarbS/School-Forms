from .models import AuditLog

_FORBIDDEN = {"password", "password1", "password2", "otp", "code", "token"}


def client_ip(request):
    return request.META.get("REMOTE_ADDR") if request is not None else None


def log(request, action, obj=None, user=None, district=None, **details):
    """Write an audit entry. Sensitive keys are stripped defensively."""
    user = user or (getattr(request, "user", None) if request is not None else None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    details = {k: v for k, v in details.items() if k.lower() not in _FORBIDDEN}
    if district is None and obj is not None:
        district = getattr(obj, "district", None) or getattr(getattr(obj, "school", None), "district", None)
    return AuditLog.objects.create(
        user=user, actor_email=getattr(user, "email", "") if user else details.pop("actor_email", ""),
        action=action, object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=str(getattr(obj, "pk", "")) if obj is not None else "",
        district=district, details=details, ip_address=client_ip(request))
