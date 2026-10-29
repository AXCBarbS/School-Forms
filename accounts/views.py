
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit.services import log
from . import throttle
from .forms import (
    EmailChangeForm,
    LoginForm,
    OTPForm,
    RegistrationForm,
    TemporaryPasswordChangeForm,
)
from .models import Approval, OTPChallenge, PasswordResetRequest, Role, User
from .otp import OTPCooldown, OTPLimit, OTPSendError, issue_otp, verify_otp


logger = logging.getLogger(__name__)

SESSION_EMAIL_CHANGE = "email_change_user_id"


def _send(request, user, purpose, new_email=""):
    """Send an OTP for supported verification workflows."""
    try:
        issue_otp(user, purpose, new_email)
        messages.success(
    request,
    "Registration submitted successfully. Your account is awaiting "
    "approval by the System Administrator. You can sign in once "
    "your account is approved.",
)
        return True
    except OTPCooldown as exc:
        messages.warning(
            request,
            f"Please wait {exc.remaining} seconds before requesting another code.",
        )
    except OTPLimit:
        messages.error(
            request,
            "Too many codes requested. Try again later.",
        )
    except OTPSendError:
        messages.error(
            request,
            "The verification email could not be sent. Please try again later.",
        )

    return False


@throttle.limit_requests("register", 20, 3600)
def register(request):
    """Register a user and require administrator approval."""
    if request.user.is_authenticated:
        if request.user.must_change_password:
            return redirect("accounts:temporary_password_change")
        return redirect("enrollment:dashboard")

    form = RegistrationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data

        with transaction.atomic():
            user = User.objects.create_user(
                data["email"],
                data["password1"],
                full_name=data["full_name"],
                district=data["district"],
                role=Role.USER,
                email_verified=True,
                approval_status=Approval.PENDING,
            )

            log(
                request,
                "register",
                user,
                user=None,
                actor_email=user.email,
                district=user.district,
            )

        messages.success(
            request,
            "Registration submitted successfully. Your account is awaiting "
            "approval by your district administrator. You can sign in once "
            "your account is approved.",
        )
        return redirect("accounts:login")

    return render(request, "accounts/register.html", {"form": form})


def verify(request):
    """Legacy registration OTP endpoint; registration no longer uses OTP."""
    messages.info(
        request,
        "Registration no longer requires an email verification code. "
        "Please sign in or contact your administrator if you need assistance.",
    )
    return redirect("accounts:login")


@require_POST
@throttle.limit_requests("otp_resend_ip", 15, 3600)
def resend(request):
    """Registration OTP resend is disabled."""
    messages.info(
        request,
        "Registration no longer requires an email verification code.",
    )
    return redirect("accounts:login")


def user_login(request):
    if request.user.is_authenticated:
        if request.user.must_change_password:
            return redirect("accounts:temporary_password_change")
        return redirect("enrollment:dashboard")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        ident = f"{request.META.get('REMOTE_ADDR', '?')}|{email}"

        if throttle.is_blocked("login", ident, settings.LOGIN_MAX_FAILURES):
            form.add_error(
                None,
                "Too many failed attempts. Try again in a few minutes.",
            )
            log(request, "login_blocked", user=None, actor_email=email)
        else:
            user, problem = form.get_user(request)

            if problem is None and user is not None:
                if user.must_change_password and user.temporary_password_expired:
                    problem = "temporary_expired"
                else:
                    throttle.reset("login", ident)
                    login(request, user)
                    log(request, "login", user)

                    if user.must_change_password:
                        return redirect("accounts:temporary_password_change")

                    next_url = request.POST.get("next") or request.GET.get("next")
                    if next_url and url_has_allowed_host_and_scheme(
                        next_url,
                        {request.get_host()},
                        request.is_secure(),
                    ):
                        return redirect(next_url)

                    return redirect("enrollment:dashboard")

            if problem is not None:
                throttle.add_failure(
                    "login",
                    ident,
                    settings.LOGIN_LOCKOUT_SECONDS,
                )
                log(
                    request,
                    "login_failed",
                    user=None,
                    actor_email=email,
                    reason=problem,
                )

                error_messages = {
                    "invalid": "Invalid email or password.",
                    "unverified": (
                        "This account has not verified its email. "
                        "Please contact your administrator if you need assistance."
                    ),
                    "pending": (
                        "Your registration is awaiting approval "
                        "by your district administrator."
                    ),
                    "rejected": (
                        "Your registration was not approved. "
                        "Contact your district administrator."
                    ),
                    "suspended": (
                        "This account is suspended. Contact your administrator."
                    ),
                    "temporary_expired": (
                        "Your temporary password has expired. Submit a new "
                        "password-reset request and wait for administrator review."
                    ),
                }
                form.add_error(
                    None,
                    error_messages.get(
                        problem,
                        "Unable to log in. Please contact your administrator.",
                    ),
                )

    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


@require_POST
def user_logout(request):
    if request.user.is_authenticated:
        log(request, "logout", request.user)

    logout(request)
    return redirect("accounts:login")


@login_required
@throttle.limit_requests("email_change", 20, 3600)
def email_change(request):
    if request.user.must_change_password:
        return redirect("accounts:temporary_password_change")

    form = EmailChangeForm(request.user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        if _send(
            request,
            request.user,
            OTPChallenge.Purpose.EMAIL_CHANGE,
            form.cleaned_data["new_email"],
        ):
            request.session["email_change_new_email"] = form.cleaned_data["new_email"]
            request.session[SESSION_EMAIL_CHANGE] = request.user.pk
            return redirect("accounts:email_change_verify")

    return render(request, "accounts/email_change.html", {"form": form})


@login_required
@throttle.limit_requests("email_change_verify", 30, 600)
def email_change_verify(request):
    if request.user.must_change_password:
        return redirect("accounts:temporary_password_change")

    if request.session.get(SESSION_EMAIL_CHANGE) != request.user.pk:
        return redirect("accounts:email_change")

    form = OTPForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ok, reason, challenge = verify_otp(
            request.user,
            OTPChallenge.Purpose.EMAIL_CHANGE,
            form.cleaned_data["code"],
        )

        if ok:
            if challenge is None or not challenge.new_email:
                form.add_error(
                    "code",
                    "The verification request is invalid. Please try again.",
                )
            elif User.objects.filter(
                email__iexact=challenge.new_email
            ).exclude(pk=request.user.pk).exists():
                messages.error(request, "That email address is no longer available.")
                return redirect("accounts:email_change")
            else:
                old_email = request.user.email
                request.user.email = challenge.new_email
                request.user.save(update_fields=["email"])

                request.session.pop(SESSION_EMAIL_CHANGE, None)
                request.session.pop("email_change_new_email", None)

                log(
                    request,
                    "email_changed",
                    request.user,
                    old_email=old_email,
                    new_email=challenge.new_email,
                )
                messages.success(request, "Your email address was updated.")
                return redirect("enrollment:dashboard")

        else:
            error_messages = {
                "wrong": "Incorrect code.",
                "expired": "That code has expired.",
                "locked": "Too many incorrect attempts.",
                "none": "No active code.",
            }
            form.add_error(
                "code",
                error_messages.get(reason, "Verification failed."),
            )

    return render(
        request,
        "accounts/verify.html",
        {
            "form": form,
            "target": "your new email address",
            "resend_url": None,
            "title": "Confirm new email",
        },
    )


@throttle.limit_requests("pwreset", 10, 3600)
def password_reset(request):
    """
    Create a password-reset request for System Admin review.
    No emails, OTPs, or reset links are sent.
    """
    if request.method != "POST":
        return render(request, "accounts/password_reset_form.html")

    email = request.POST.get("email", "").strip().lower()

    if email:
        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
            email_verified=True,
            approval_status=Approval.APPROVED,
        ).first()

        if user:
            with transaction.atomic():
                existing_request = PasswordResetRequest.objects.filter(
                    user=user,
                    status=PasswordResetRequest.Status.PENDING,
                ).first()

                reset_request = None

                if existing_request is None:
                    reset_request = PasswordResetRequest.objects.create(
                        user=user
                    )

            if reset_request is not None:
                log(
                    request,
                    "password_reset_requested",
                    reset_request,
                    target_email=user.email,
                )

    # Use the same response whether the account exists or not.
    # No email or other external notification is sent.
    return redirect("accounts:password_reset_done")


def password_reset_done(request):
    return render(request, "accounts/password_reset_done.html")


def password_reset_confirm(request, uidb64=None, token=None):
    """Legacy reset links are no longer accepted."""
    messages.info(
        request,
        "Password resets require administrator approval. "
        "Please submit a password-reset request.",
    )
    return redirect("accounts:password_reset")


def password_reset_complete(request):
    return render(request, "accounts/password_reset_complete.html")


@login_required
@throttle.limit_requests("temporary_password_change", 10, 3600)
def temporary_password_change(request):
    """Require users with temporary passwords to choose a permanent password."""
    user = request.user

    if not user.must_change_password:
        return redirect("enrollment:dashboard")

    if user.temporary_password_expired:
        logout(request)
        messages.error(
            request,
            "Your temporary password has expired. Submit a new password-reset "
            "request and wait for administrator review.",
        )
        return redirect("accounts:password_reset")

    form = TemporaryPasswordChangeForm(user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        new_password = form.cleaned_data["new_password1"]

        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            form.add_error("new_password1", exc)
        else:
            user.set_password(new_password)
            user.must_change_password = False
            user.temporary_password_expires_at = None
            user.save(
                update_fields=[
                    "password",
                    "must_change_password",
                    "temporary_password_expires_at",
                ]
            )

            # Keep the user signed in after changing their password.
            login(request, user)

            log(
                request,
                "temporary_password_changed",
                user,
                target_email=user.email,
            )
            messages.success(request, "Your password has been changed successfully.")
            return redirect("enrollment:dashboard")

    return render(
        request,
        "accounts/temporary_password_change.html",
        {"form": form},
    )
