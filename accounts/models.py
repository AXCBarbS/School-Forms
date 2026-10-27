from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Role(models.TextChoices):
    SYSTEM_ADMIN = "system_admin", "System administrator"
    DISTRICT_ADMIN = "district_admin", "District administrator"
    USER = "user", "District user"


class Approval(models.TextChoices):
    PENDING = "pending", "Pending approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _make(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", Role.USER)
        return self._make(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(role=Role.SYSTEM_ADMIN, is_staff=True, is_superuser=True,
                     email_verified=True, approval_status=Approval.APPROVED)
        return self._make(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=254, unique=True)
    full_name = models.CharField(max_length=150)
    district = models.ForeignKey("organization.District", null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="users")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    email_verified = models.BooleanField(default=False)
    approval_status = models.CharField(max_length=10, choices=Approval.choices, default=Approval.PENDING)
    approved_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, help_text="Untick to suspend the account.")
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci"),
            models.CheckConstraint(
                condition=models.Q(role="system_admin") | models.Q(district__isnull=False),
                name="non_system_admin_requires_district"),
        ]
        indexes = [models.Index(fields=["district", "approval_status"])]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name

    @property
    def is_system_admin(self):
        return self.role == Role.SYSTEM_ADMIN

    @property
    def is_district_admin(self):
        return self.role == Role.DISTRICT_ADMIN

    @property
    def can_manage_users(self):
        return self.role in (Role.SYSTEM_ADMIN, Role.DISTRICT_ADMIN)

    @property
    def is_fully_active(self):
        return self.is_active and self.email_verified and self.approval_status == Approval.APPROVED


class OTPChallenge(models.Model):
    class Purpose(models.TextChoices):
        REGISTER = "register", "Registration"
        EMAIL_CHANGE = "email_change", "Email change"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otp_challenges")
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    new_email = models.EmailField(blank=True)
    salt = models.CharField(max_length=32)
    code_hash = models.CharField(max_length=64)           # HMAC-SHA256, never the plaintext code
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "-created_at"])]
