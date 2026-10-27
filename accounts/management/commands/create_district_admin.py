from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.contrib.auth import password_validation
from django.utils import timezone

from accounts.models import Approval, Role, User
from accounts.validators import validate_deped_email
from organization.models import District


class Command(BaseCommand):
    help = "Create (or promote) a district administrator for a district."

    def add_arguments(self, p):
        p.add_argument("email")
        p.add_argument("full_name")
        p.add_argument("district", help="District name exactly as in the master list, e.g. 'La Trinidad'")
        p.add_argument("--password", help="If omitted you are prompted (preferred).")

    def handle(self, *a, **o):
        try:
            email = validate_deped_email(o["email"])
        except ValidationError as exc:
            raise CommandError(exc.messages[0])
        try:
            district = District.objects.get(name__iexact=o["district"])
        except District.DoesNotExist:
            raise CommandError(f"Unknown district: {o['district']}")
        pw = o["password"] or getpass("Password: ")
        try:
            password_validation.validate_password(pw)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))
        user, created = User.objects.get_or_create(email=email, defaults=dict(full_name=o["full_name"], district=district))
        user.full_name, user.district, user.role = o["full_name"], district, Role.DISTRICT_ADMIN
        user.email_verified, user.approval_status, user.approved_at = True, Approval.APPROVED, timezone.now()
        user.set_password(pw)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} district admin {email} for {district}"))
