
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.http import HttpResponse

from accounts.models import Approval, PasswordResetRequest, Role, User
from audit.models import AuditLog
from audit.services import log
from organization.importer import apply_import, parse_workbook, reconcile
from organization.models import District, School

from .access import manager_required, system_admin_required
from .models import EnrollmentRecord, RecordStatus
from .services import STATE_LABELS, record_state


def _managed_users(user):
    qs = User.objects.select_related("district")
    if user.is_system_admin:
        return qs
    # District admins only see ordinary users in their own district.
    return qs.filter(district_id=user.district_id, role=Role.USER)


@manager_required
def users(request):
    qs = _managed_users(request.user)
    status = request.GET.get("status", "pending")

    if status == "pending":
        qs = qs.filter(
            email_verified=True,
            approval_status=Approval.PENDING,
        )
    elif status == "unverified":
        qs = qs.filter(email_verified=False)
    elif status in (Approval.APPROVED, Approval.REJECTED):
        qs = qs.filter(approval_status=status)
    elif status == "suspended":
        qs = qs.filter(is_active=False)

    page = Paginator(
        qs.order_by("district__name", "email"),
        50,
    ).get_page(request.GET.get("page"))

    return render(
        request,
        "manage/users.html",
        {"page": page, "status": status},
    )


@require_POST
@manager_required
def user_action(request, pk, action):
    target = get_object_or_404(
        _managed_users(request.user),
        pk=pk,
    )

    if target.pk == request.user.pk:
        raise PermissionDenied

    if action == "approve":
        if not target.email_verified:
            messages.error(
                request,
                "The user has not verified their email yet.",
            )
            return redirect(
                reverse("manage:users") + "?status=pending"
            )

        target.approval_status = Approval.APPROVED
        target.approved_by = request.user
        target.approved_at = timezone.now()

    elif action == "reject":
        target.approval_status = Approval.REJECTED

    elif action == "suspend":
        target.is_active = False

    elif action == "reactivate":
        target.is_active = True

    else:
        raise PermissionDenied

    target.save()

    log(
        request,
        f"user_{action}",
        target,
        district=target.district,
        target_email=target.email,
    )

    if action == "approve":
        messages.success(
            request,
            f"{target.email} has been approved successfully.",
        )
    else:
        messages.success(
            request,
            f"{target.email}: {action} done.",
        )

    allowed_statuses = {
        "pending",
        "unverified",
        "approved",
        "rejected",
        "suspended",
    }

    status = request.POST.get("status", "").strip()
    next_value = request.POST.get("next", "").strip()

    if next_value:
        if next_value.startswith("?"):
            query_status = parse_qs(
                urlsplit(next_value).query
            ).get("status", [""])[0]

            if query_status:
                status = query_status

        elif url_has_allowed_host_and_scheme(
            next_value,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            query_status = parse_qs(
                urlsplit(next_value).query
            ).get("status", [""])[0]

            if query_status:
                status = query_status

    if status not in allowed_statuses:
        status = "pending"

    return redirect(
        f"{reverse('manage:users')}?status={status}"
    )


@manager_required
def progress(request):
    user = request.user
    schools = School.objects.filter(is_active=True)

    if not user.is_system_admin:
        schools = schools.filter(district_id=user.district_id)

    year = settings.CURRENT_SCHOOL_YEAR

    recs = {
        r.school_id: r
        for r in EnrollmentRecord.objects.filter(
            school__in=schools,
            school_year=year,
        )
    }

    per = {}

    for school in schools.select_related("district"):
        state = record_state(recs.get(school.id))
        district_data = per.setdefault(
            school.district.name,
            {key: 0 for key in STATE_LABELS} | {"total": 0},
        )
        district_data[state] += 1
        district_data["total"] += 1

    rows = [
        {
            "district": name,
            **values,
            "pct": (
                round(100 * values["completed"] / values["total"])
                if values["total"]
                else 0
            ),
        }
        for name, values in sorted(per.items())
    ]

    return render(
        request,
        "manage/progress.html",
        {"rows": rows, "year": year, "labels": STATE_LABELS},
    )


@manager_required
def audit_log(request):
    qs = AuditLog.objects.select_related("user", "district")

    if not request.user.is_system_admin:
        qs = qs.filter(district_id=request.user.district_id)

    actions = (
        qs.order_by()
        .values_list("action", flat=True)
        .distinct()
        .order_by("action")
    )

    action = request.GET.get("action", "")
    if action:
        qs = qs.filter(action=action)

    page = Paginator(qs, 50).get_page(request.GET.get("page"))

    return render(
        request,
        "manage/audit.html",
        {"page": page, "actions": actions, "action": action},
    )


@system_admin_required
def import_view(request):
    report = recon = None

    if request.method == "POST" and request.FILES.get("workbook"):
        uploaded_file = request.FILES["workbook"]

        if (
            not uploaded_file.name.lower().endswith(".xlsx")
            or uploaded_file.size > 15 * 1024 * 1024
        ):
            messages.error(
                request,
                "Upload an .xlsx file smaller than 15 MB.",
            )
        else:
            try:
                parsed = parse_workbook(uploaded_file)
            except Exception:
                messages.error(
                    request,
                    "The file could not be read as an Excel workbook.",
                )
            else:
                dry_run = request.POST.get("dry_run") == "on"
                with_enrollment = (
                    request.POST.get("with_enrollment") == "on"
                )

                report = apply_import(
                    parsed,
                    with_enrollment=with_enrollment,
                    dry_run=dry_run,
                    user=request.user,
                )

                log(
                    request,
                    "import_dry_run" if dry_run else "import",
                    filename=uploaded_file.name,
                    committed=report["committed"],
                    errors=len(report["errors"]),
                    schools_created=report["schools_created"],
                )

                if report["committed"] and with_enrollment:
                    recon = reconcile(parsed)

    return render(
        request,
        "manage/import.html",
        {"report": report, "recon": recon},
    )


@system_admin_required
def password_reset_requests(request):
    status = request.GET.get("status", "pending")
    valid_statuses = {
        choice[0]
        for choice in PasswordResetRequest.Status.choices
    }

    if status not in valid_statuses:
        status = PasswordResetRequest.Status.PENDING

    requests_page = Paginator(
        PasswordResetRequest.objects.select_related(
            "user",
            "user__district",
            "reviewed_by",
        ).filter(
            status=status
        ).order_by("-requested_at"),
        30,
    ).get_page(request.GET.get("page"))

    return render(
        request,
        "manage/password_reset_requests.html",
        {
            "requests_page": requests_page,
            "status": status,
            "statuses": PasswordResetRequest.Status.choices,
        },
    )


@require_POST
@system_admin_required
def password_reset_request_action(request, pk, action):
    """Approve or reject a password-reset request."""

    if action not in {"approve", "reject"}:
        raise PermissionDenied

    with transaction.atomic():
        reset_request = get_object_or_404(
            PasswordResetRequest.objects.select_for_update().select_related(
                "user"
            ),
            pk=pk,
        )

        if reset_request.status != PasswordResetRequest.Status.PENDING:
            messages.error(
                request,
                "This request has already been reviewed.",
            )
            return redirect("manage:password_reset_requests")

        user = reset_request.user

        if action == "reject":
            reset_request.status = PasswordResetRequest.Status.REJECTED
            reset_request.reviewed_by = request.user
            reset_request.reviewed_at = timezone.now()
            reset_request.save(
                update_fields=[
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                ]
            )

            log(
                request,
                "password_reset_request_rejected",
                reset_request,
                target_email=user.email,
            )

            messages.success(
                request,
                "Password-reset request rejected.",
            )
            return redirect("manage:password_reset_requests")

        if not user.is_fully_active:
            messages.error(
                request,
                "This account is not active, verified, and approved. "
                "The password-reset request cannot be approved.",
            )
            return redirect("manage:password_reset_requests")

        # Generate a strong, unpredictable temporary password.
        # It is never stored in plaintext in the database.
        temporary_password = secrets.token_urlsafe(18)
        expires_at = timezone.now() + timedelta(hours=24)

        user.set_password(temporary_password)
        user.must_change_password = True
        user.temporary_password_expires_at = expires_at
        user.save(
            update_fields=[
                "password",
                "must_change_password",
                "temporary_password_expires_at",
            ]
        )

        reset_request.status = PasswordResetRequest.Status.APPROVED
        reset_request.reviewed_by = request.user
        reset_request.reviewed_at = timezone.now()
        reset_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
            ]
        )

        log(
            request,
            "password_reset_request_approved",
            reset_request,
            target_email=user.email,
            temporary_password_expires_at=expires_at.isoformat(),
        )

    # Show the password only in this immediate response.
    # Do not put it in messages, the URL, or the audit log.
    # The admin must securely relay it to the account owner.
    response_html = f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Temporary Password Generated</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 720px;
                margin: 48px auto;
                padding: 0 20px;
                line-height: 1.6;
                color: #222;
            }}
            .password {{
                padding: 16px;
                border: 1px solid #ccc;
                border-radius: 8px;
                overflow-wrap: anywhere;
                font-family: monospace;
                font-size: 1.2rem;
                background: #f6f6f6;
            }}
            .warning {{
                color: #8a3b00;
            }}
            a {{
                display: inline-block;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <h1>Temporary Password Generated</h1>
        <p>The password reset was approved for
        <strong>{escape(user.email)}</strong>.</p>
        <p>Temporary password:</p>
        <div class="password">{escape(temporary_password)}</div>
        <p><strong>Expires:</strong> {escape(expires_at.strftime("%Y-%m-%d %H:%M %Z"))}</p>
        <p class="warning">
            Relay this password to the user through an approved secure channel.
            It will not be emailed by the portal. The user must change it at
            their next login. Do not share it with anyone else.
        </p>
        <p>This page displays the password only for this response.
        Once you leave or refresh it, the portal will not be able to show
        this same password again.</p>
        <a href="{escape(reverse('manage:password_reset_requests'))}">
            Return to password-reset requests
        </a>
    </body>
    </html>
    """

    response = HttpResponse(response_html)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    return response
