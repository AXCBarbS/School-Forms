
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audit.services import log
from . import throttle
from .forms import (
    ActivePasswordResetForm,
    EmailChangeForm,
    LoginForm,
    OTPForm,
    RegistrationForm,
)
from .models import Approval, OTPChallenge, Role, User
from .otp import (
    OTPCooldown,
    OTPLimit,
    OTPSendError,
    issue_otp,
    verify_otp,
)

SESSION_VERIFY = "verify_user_id"
SESSION_EMAIL_CHANGE = "email_change_user_id"


def _send(request, user, purpose, new_email=""):
    """Send an OTP for features that still require email verification."""
    try:
        issue_otp(user, purpose, new_email)
        messages.success(
            request,
            "A 6-digit verification code was sent to "
            + (new_email or user.email)
            + ".",
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


@throttle.limit_requests("register", 20, 3600)
def register(request):
    """Register without OTP; district administrator approval is required."""
    if request.user.is_authenticated:
        return redirect("enrollment:dashboard")

    form = RegistrationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data

        with transaction.atomic():
            user = User.objects.create_user(
                cd["email"],
                cd["password1"],
                full_name=cd["full_name"],
                district=cd["district"],
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
            "Registration successful. Your account is awaiting approval "
            "by your district administrator. You can sign in once approved.",
        )
        return redirect("accounts:login")

    return render(request, "accounts/register.html", {"form": form})




@throttle.limit_requests("otp_verify_ip", 30, 600)
def verify(request):
    """Retained for existing registrations that still need OTP verification."""
    user = User.objects.filter(
        pk=request.session.get(SESSION_VERIFY),
        email_verified=False,
    ).first()

    if user is None:
        messages.info(
            request,
            "Start by registering or signing in.",
        )
        return redirect("accounts:login")

    form = OTPForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ok, reason, _ = verify_otp(
            user,
            OTPChallenge.Purpose.REGISTER,
            form.cleaned_data["code"],
        )

        if ok:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            request.session.pop(SESSION_VERIFY, None)

            log(
                request,
                "email_verified",
                user,
                user=None,
                actor_email=user.email,
                district=user.district,
            )

            messages.success(
                request,
                "Email verified. Your district membership now awaits approval "
                "by your district administrator. You can sign in once approved.",
            )
            return redirect("accounts:login")

        msg = {
            "wrong": "Incorrect code.",
            "expired": "That code has expired. Request a new one.",
            "locked": "Too many incorrect attempts. Request a new code.",
            "none": "No active code. Request a new one.",
        }.get(reason, "Verification failed. Please try again.")

        form.add_error("code", msg)

        log(
            request,
            "otp_failed",
            user,
            user=None,
            actor_email=user.email,
            reason=reason,
        )

    return render(
        request,
        "accounts/verify.html",
        {
            "form": form,
            "target": user.email,
            "resend_url": "accounts:resend",
        },
    )


@require_POST
@throttle.limit_requests("otp_resend_ip", 15, 3600)
def resend(request):
    """Retained for existing registrations that still need OTP verification."""
    user = User.objects.filter(
        pk=request.session.get(SESSION_VERIFY),
        email_verified=False,
    ).first()

    if user is None:
        return redirect("accounts:login")

    _send(request, user, OTPChallenge.Purpose.REGISTER)
    return redirect("accounts:verify")


def user_login(request):
    """Authenticate users without redirecting them to email OTP verification."""
    if request.user.is_authenticated:
        return redirect("enrollment:dashboard")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ident = (
            f"{request.META.get('REMOTE_ADDR', '?')}|"
            f"{form.cleaned_data['email'].strip().lower()}"
        )

        if throttle.is_blocked(
            "login",
            ident,
            settings.LOGIN_MAX_FAILURES,
        ):
            form.add_error(
                None,
                "Too many failed attempts. Try again in a few minutes.",
            )

            log(
                request,
                "login_blocked",
                user=None,
                actor_email=form.cleaned_data["email"],
            )

        else:
            user, problem = form.get_user(request)

            if problem is None:
                throttle.reset("login", ident)
                login(request, user)
                log(request, "login", user)

                nxt = request.POST.get("next") or request.GET.get("next")

                if nxt and url_has_allowed_host_and_scheme(
                    nxt,
                    {request.get_host()},
                    request.is_secure(),
                ):
                    return redirect(nxt)

                return redirect("enrollment:dashboard")

            throttle.add_failure(
                "login",
                ident,
                settings.LOGIN_LOCKOUT_SECONDS,
            )

            log(
                request,
                "login_failed",
                user=None,
                actor_email=form.cleaned_data["email"],
                reason=problem,
            )

            form.add_error(
                None,
                {
                    "invalid": "Invalid email or password.",
                    "unverified": (
                        "This account has not been marked as email verified. "
                        "Please contact your administrator."
                    ),
                    "pending": (
                        "Your registration is awaiting approval by your "
                        "district administrator."
                    ),
                    "rejected": (
                        "Your registration was not approved. "
                        "Contact your district administrator."
                    ),
                    "suspended": (
                        "This account is suspended. Contact your administrator."
                    ),
                }.get(
                    problem,
                    "Unable to sign in. Please contact your administrator.",
                ),
            )

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "next": request.GET.get("next", ""),
        },
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
    """Email changes still require OTP verification."""
    form = EmailChangeForm(request.user, request.POST or None)

    if request.method == "POST" and form.is_valid():
        if _send(
            request,
            request.user,
            OTPChallenge.Purpose.EMAIL_CHANGE,
            form.cleaned_data["new_email"],
        ):
            request.session[SESSION_EMAIL_CHANGE] = request.user.pk
            return redirect("accounts:email_change_verify")

    return render(
        request,
        "accounts/email_change.html",
        {"form": form},
    )


@login_required
@throttle.limit_requests("email_change_verify", 30, 600)
def email_change_verify(request):
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
            if User.objects.filter(
                email__iexact=challenge.new_email
            ).exclude(pk=request.user.pk).exists():
                messages.error(
                    request,
                    "That email address is no longer available.",
                )
                return redirect("accounts:email_change")

            old_email = request.user.email
            request.user.email = challenge.new_email
            request.user.save(update_fields=["email"])
            request.session.pop(SESSION_EMAIL_CHANGE, None)

            log(
                request,
                "email_changed",
                request.user,
                old_email=old_email,
                new_email=challenge.new_email,
            )

            messages.success(
                request,
                "Your email address was updated.",
            )
            return redirect("enrollment:dashboard")

        form.add_error(
            "code",
            {
                "wrong": "Incorrect code.",
                "expired": "That code has expired.",
                "locked": "Too many incorrect attempts.",
                "none": "No active code.",
            }.get(reason, "Verification failed. Please try again."),
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


class ThrottledPasswordResetView(PasswordResetView):
    form_class = ActivePasswordResetForm
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            if (
                throttle.add_failure(
                    "pwreset",
                    request.META.get("REMOTE_ADDR", "?"),
                    3600,
                )
                > 10
            ):
                from django.http import HttpResponse

                return HttpResponse(
                    "Too many requests. Please wait and try again.",
                    status=429,
                )

        return super().dispatch(request, *args, **kwargs)


password_reset = ThrottledPasswordResetView.as_view()

password_reset_done = PasswordResetDoneView.as_view(
    template_name="accounts/password_reset_done.html",
)

password_reset_confirm = PasswordResetConfirmView.as_view(
    template_name="accounts/password_reset_confirm.html",
    success_url=reverse_lazy("accounts:password_reset_complete"),
)

password_reset_complete = PasswordResetCompleteView.as_view(
    template_name="accounts/password_reset_complete.html",
)
