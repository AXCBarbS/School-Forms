from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm
from django.utils import timezone

from .models import Approval, OTPChallenge, User


class UserCreateForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name", "district", "role")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreateForm
    ordering = ("email",)
    list_display = ("email", "full_name", "district", "role", "email_verified", "approval_status", "is_active")
    list_filter = ("role", "approval_status", "email_verified", "is_active", "district")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "district", "role")}),
        ("Status", {"fields": ("email_verified", "approval_status", "is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "district", "role",
                                                               "usable_password", "password1", "password2")}),)
    actions = ["approve", "reject"]

    @admin.action(description="Approve selected users")
    def approve(self, request, qs):
        qs.update(approval_status=Approval.APPROVED, approved_by=request.user, approved_at=timezone.now())

    @admin.action(description="Reject selected users")
    def reject(self, request, qs):
        qs.update(approval_status=Approval.REJECTED)


@admin.register(OTPChallenge)
class OTPAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "created_at", "expires_at", "attempts", "consumed_at")
    exclude = ("salt", "code_hash")
    readonly_fields = ("user", "purpose", "new_email", "created_at", "last_sent_at", "expires_at", "attempts",
                       "consumed_at")

    def has_add_permission(self, request):
        return False
