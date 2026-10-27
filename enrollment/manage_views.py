from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Approval, Role, User
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
    # district admins only ever see ordinary users of their own district
    return qs.filter(district_id=user.district_id, role=Role.USER)


@manager_required
def users(request):
    qs = _managed_users(request.user)
    status = request.GET.get("status", "pending")
    if status == "pending":
        qs = qs.filter(email_verified=True, approval_status=Approval.PENDING)
    elif status == "unverified":
        qs = qs.filter(email_verified=False)
    elif status in (Approval.APPROVED, Approval.REJECTED):
        qs = qs.filter(approval_status=status)
    elif status == "suspended":
        qs = qs.filter(is_active=False)
    page = Paginator(qs.order_by("district__name", "email"), 50).get_page(request.GET.get("page"))
    return render(request, "manage/users.html", {"page": page, "status": status})


@require_POST
@manager_required
def user_action(request, pk, action):
    target = get_object_or_404(_managed_users(request.user), pk=pk)      # scope enforced here
    if target.pk == request.user.pk:
        raise PermissionDenied
    if action == "approve":
        if not target.email_verified:
            messages.error(request, "The user has not verified their email yet.")
            return redirect("manage:users")
        target.approval_status, target.approved_by, target.approved_at = Approval.APPROVED, request.user, timezone.now()
    elif action == "reject":
        target.approval_status = Approval.REJECTED
    elif action == "suspend":
        target.is_active = False
    elif action == "reactivate":
        target.is_active = True
    else:
        raise PermissionDenied
    target.save()
    log(request, f"user_{action}", target, district=target.district, target_email=target.email)
    messages.success(request, f"{target.email}: {action} done.")
    return redirect(request.POST.get("next") or "manage:users")


@manager_required
def progress(request):
    user = request.user
    schools = School.objects.filter(is_active=True)
    if not user.is_system_admin:
        schools = schools.filter(district_id=user.district_id)
    year = settings.CURRENT_SCHOOL_YEAR
    recs = {r.school_id: r for r in EnrollmentRecord.objects.filter(school__in=schools, school_year=year)}
    per = {}
    for s in schools.select_related("district"):
        st = record_state(recs.get(s.id))
        d = per.setdefault(s.district.name, {k: 0 for k in STATE_LABELS} | {"total": 0})
        d[st] += 1
        d["total"] += 1
    rows = [{"district": n, **v, "pct": round(100 * v["completed"] / v["total"]) if v["total"] else 0}
            for n, v in sorted(per.items())]
    return render(request, "manage/progress.html", {"rows": rows, "year": year, "labels": STATE_LABELS})


@manager_required
def audit_log(request):
    qs = AuditLog.objects.select_related("user", "district")
    if not request.user.is_system_admin:
        qs = qs.filter(district_id=request.user.district_id)
    actions = qs.order_by().values_list("action", flat=True).distinct().order_by("action")   # scoped, no leakage
    action = request.GET.get("action", "")
    if action:
        qs = qs.filter(action=action)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "manage/audit.html", {"page": page, "actions": actions, "action": action})


@system_admin_required
def import_view(request):
    report = recon = None
    if request.method == "POST" and request.FILES.get("workbook"):
        f = request.FILES["workbook"]
        if not f.name.lower().endswith(".xlsx") or f.size > 15 * 1024 * 1024:
            messages.error(request, "Upload an .xlsx file smaller than 15 MB.")
        else:
            try:
                parsed = parse_workbook(f)
            except Exception:
                messages.error(request, "The file could not be read as an Excel workbook.")
            else:
                dry = request.POST.get("dry_run") == "on"
                with_enr = request.POST.get("with_enrollment") == "on"
                report = apply_import(parsed, with_enrollment=with_enr, dry_run=dry, user=request.user)
                log(request, "import_dry_run" if dry else "import", filename=f.name, committed=report["committed"],
                    errors=len(report["errors"]), schools_created=report["schools_created"])
                if report["committed"] and with_enr:
                    recon = reconcile(parsed)
    return render(request, "manage/import.html", {"report": report, "recon": recon})
