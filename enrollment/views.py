from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from audit.services import log
from .access import accessible_schools, can_manage_district, get_school_or_404
from .exports import build_export
from .forms import EnrollmentForm
from .models import EnrollmentRecord, RecordStatus
from .schema import AGGREGATES, LEVELS, SECTION_TITLES
from .services import (STATE_LABELS, compute_totals, get_or_create_record, record_state, record_values,
                       reopen_record, save_values, submit_problems, submit_record)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def school_rows(schools):
    year = settings.CURRENT_SCHOOL_YEAR
    recs = {r.school_id: r for r in EnrollmentRecord.objects.filter(school__in=schools, school_year=year)}
    rows = []
    for s in schools:
        rec = recs.get(s.id)
        state = record_state(rec)
        rows.append({"school": s, "record": rec, "state": state,
                     "label": STATE_LABELS[state][0], "badge": STATE_LABELS[state][1]})
    return rows


@login_required
def dashboard(request):
    user = request.user
    schools = accessible_schools(user)
    district_filter = request.GET.get("district", "")
    if user.is_system_admin and district_filter.isdigit():
        schools = schools.filter(district_id=int(district_filter))
    q = request.GET.get("q", "").strip()
    if q:
        schools = schools.filter(Q(name__icontains=q) | Q(school_id__icontains=q))
    rows = school_rows(schools)
    counts = {k: 0 for k in STATE_LABELS}
    for r in rows:
        counts[r["state"]] += 1
    state = request.GET.get("state", "")
    if state in STATE_LABELS:
        rows = [r for r in rows if r["state"] == state]
    page = Paginator(rows, 50).get_page(request.GET.get("page"))
    ctx = {"page": page, "q": q, "state": state, "counts": counts, "total": sum(counts.values()),
           "states": [(k, v[0]) for k, v in STATE_LABELS.items()], "year": settings.CURRENT_SCHOOL_YEAR}
    if user.is_system_admin:
        from organization.models import District
        ctx["districts"] = District.objects.filter(is_active=True)
        ctx["district_filter"] = district_filter
    return render(request, "enrollment/dashboard.html", ctx)


def _sections(form=None, totals=None):
    """Template-friendly structure: [(code, title, [row,...])] where row has key, label and either
    bound form fields (entry page) or calculated M/F/T (review page)."""
    out = []
    for code, title in SECTION_TITLES.items():
        rows = []
        for k, label, sec, _c in LEVELS:
            if sec != code:
                continue
            row = {"key": k, "label": label}
            if form is not None:
                row["m"], row["f"] = form[f"{k}_m"], form[f"{k}_f"]
            if totals is not None:
                row["mt"], row["ft"], row["tt"] = totals[k]
            rows.append(row)
        out.append((code, title, rows))
    return out


def _agg_rows():
    return [(k, v[0]) for k, v in AGGREGATES.items()]


@login_required
def school_entry(request, school_id):
    school = get_school_or_404(request.user, school_id)
    record = get_or_create_record(school, request.user)
    if record.status == RecordStatus.SUBMITTED:
        messages.info(request, "This record has been submitted and is locked. Ask a district administrator to reopen it.")
        return redirect("enrollment:review", school_id=school.school_id)
    if request.method == "POST":
        form = EnrollmentForm(request.POST)
        if form.is_valid():
            save_values(record, form.values(), request.user)
            log(request, "record_saved", record, district=school.district, school_id=school.school_id)
            messages.success(request, "Draft saved.")
            if request.POST.get("action") == "review":
                return redirect("enrollment:review", school_id=school.school_id)
            return redirect("enrollment:entry", school_id=school.school_id)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = EnrollmentForm(initial=EnrollmentForm.initial_from(record_values(record)))
    return render(request, "enrollment/entry.html", {
        "school": school, "record": record, "form": form, "sections": _sections(form=form), "aggs": _agg_rows(),
        "agg_parts": {k: v[1] for k, v in AGGREGATES.items()}, "year": settings.CURRENT_SCHOOL_YEAR,
        "prefilled": record_state(record) == "prefilled"})


@login_required
def school_review(request, school_id):
    school = get_school_or_404(request.user, school_id)
    record = get_or_create_record(school, request.user)
    values = record_values(record)
    totals = compute_totals(values)
    return render(request, "enrollment/review.html", {
        "school": school, "record": record, "values": values, "totals": totals, "sections": _sections(),
        "aggs": _agg_rows(), "problems": submit_problems(values), "year": settings.CURRENT_SCHOOL_YEAR,
        "can_reopen": can_manage_district(request.user, school.district_id),
        "state_label": STATE_LABELS[record_state(record)][0]})


@login_required
def school_submit(request, school_id):
    school = get_school_or_404(request.user, school_id)
    record = get_or_create_record(school, request.user)
    if record.status == RecordStatus.SUBMITTED:
        return redirect("enrollment:review", school_id=school.school_id)
    values = record_values(record)
    problems = submit_problems(values)
    if request.method == "POST":
        if problems:
            messages.error(request, "Fix the listed problems before submitting.")
        elif request.POST.get("confirm") != "yes":
            messages.error(request, "Tick the confirmation box to submit.")
        else:
            submit_record(record, request.user)
            log(request, "record_submitted", record, district=school.district, school_id=school.school_id)
            messages.success(request, f"{school.name} was submitted.")
            return redirect("enrollment:review", school_id=school.school_id)
    return render(request, "enrollment/submit.html", {
        "school": school, "totals": compute_totals(values), "problems": problems, "aggs": _agg_rows(),
        "year": settings.CURRENT_SCHOOL_YEAR})


@require_POST
@login_required
def school_reopen(request, school_id):
    school = get_school_or_404(request.user, school_id)
    if not can_manage_district(request.user, school.district_id):
        raise PermissionDenied
    record = get_or_create_record(school, request.user)
    reopen_record(record, request.user)
    log(request, "record_reopened", record, district=school.district, school_id=school.school_id)
    messages.success(request, "Record reopened for editing.")
    return redirect("enrollment:entry", school_id=school.school_id)


@login_required
def export_xlsx(request):
    schools = accessible_schools(request.user)
    district = request.GET.get("district", "")
    if request.user.is_system_admin and district.isdigit():
        schools = schools.filter(district_id=int(district))
    wb = build_export(schools)
    log(request, "export", district=request.user.district, count=schools.count())
    resp = HttpResponse(content_type=XLSX)
    resp["Content-Disposition"] = f'attachment; filename="SF4_{settings.CURRENT_SCHOOL_YEAR}.xlsx"'
    wb.save(resp)
    return resp
