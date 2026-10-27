from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def normalize_email(value):
    return (value or "").strip().lower()


def email_domain(value):
    return value.rsplit("@", 1)[1] if "@" in value else ""


def validate_deped_email(value):
    """Accept only addresses whose domain is EXACTLY one of settings.DEPED_EMAIL_DOMAINS.
    A substring test such as 'deped' in email would accept mydeped.com or deped.gov.ph.evil.com."""
    value = normalize_email(value)
    validate_email(value)
    local, _, domain = value.rpartition("@")
    if not local or domain not in set(settings.DEPED_EMAIL_DOMAINS):
        raise ValidationError("Use your official DepEd email address.", code="not_deped")
    return value
