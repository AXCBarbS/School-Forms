
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
from organization.models import School

from .access import (
    accessible_schools,
    can_manage_district,
    get_school_or_404,
)
from .exports import build_export
from .forms import EnrollmentForm
from .models import EnrollmentRecord, RecordStatus
from .schema import AGGREGATES, LEVELS, SECTION_TITLES
from .services import (
    STATE_LABELS,
    compute_totals,
    get_or_create_record,
    record_state,
    record_values,
    reopen_record,
    save_values,
    submit_problems,
    submit_record,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# School types and the SF4 sections each type is permitted to access.
SCHOOL_TYPE_SECTIONS = {
    School.ELEMENTARY: {"ES"},
    School.INTEGRATED: {"ES", "JHS", "SHS"},
    School.NATIONAL_HIGH_SCHOOL: {"JHS", "SHS"},
}


def allowed_sections(school):
    """Return the SF4 sections permitted for this school's type."""
    return SCHOOL_TYPE_SECTIONS.get(school.school_type, set())


def allowed_level_keys(school):
    """Return enrollment level keys permitted for this school's type."""
    permitted = allowed_sections(school)
    return {
        key
        for key, _label, section, _column in LEVELS
        if section in permitted
    }


def filter_school_values(school, values):
    """
    Keep every schema key, but clear values for levels not permitted
    for the school's classification.
    """
    permitted = allowed_level_keys(school)
    return {
        key: values.get(key, (None, None)) if key in permitted else (None, None)
        for key, *_ in LEVELS
    }


def has_unauthorized_posted_values(request, school):
    """Reject non-empty POST values for levels this school cannot access."""
    permitted = allowed_level_keys(school)

    for key, *_ in LEVELS:
        if key in permitted:
            continue

        for suffix in ("m", "f"):
            field_name = f"{key}_{suffix}"
            if request.POST.get(field_name, "").strip():
                return True

    return False


def school_rows(schools):
    """Build dashboard rows for the selected schools."""
    year = settings.CURRENT_SCHOOL_YEAR
    records = {
        record.school_id: record
        for record in EnrollmentRecord.objects.filter(
            school__in=schools,
            school_year=year,
        )
    }

    rows = []

    for school in schools:
        record = records.get(school.id)
        state = record_state(record)
        rows.append(
            {
                "school": school,
                "record": record,
                "state": state,
                "label": STATE_LABELS[state][0],
                "badge": STATE_LABELS[state][1],
            }
        )

    return rows


@login_required
def dashboard(request):
    user = request.user
    schools = accessible_schools(user)
    district_filter = request.GET.get("district", "")

    if user.is_system_admin and district_filter.isdigit():
        schools = schools.filter(district_id=int(district_filter))

    query = request.GET.get("q", "").strip()

    if query:
        schools = schools.filter(
            Q(name__icontains=query) | Q(school_id__icontains=query)
        )

    rows = school_rows(schools)
    counts = {key: 0 for key in STATE_LABELS}

    for row in rows:
        counts[row["state"]] += 1

    state = request.GET.get("state", "")

    if state in STATE_LABELS:
        rows = [row for row in rows if row["state"] == state]

    page = Paginator(rows, 50).get_page(request.GET.get("page"))

    context = {
        "page": page,
        "q": query,
        "state": state,
        "counts": counts,
        "total": sum(counts.values()),
        "states": [(key, value[0]) for key, value in STATE_LABELS.items()],
        "year": settings.CURRENT_SCHOOL_YEAR,
    }

    if user.is_system_admin:
        from organization.models import District

        context["districts"] = District.objects.filter(is_active=True)
        context["district_filter"] = district_filter

    return render(request, "enrollment/dashboard.html", context)


def _sections(form=None, totals=None, school=None):
    """Build template section data, restricted to the school's type if given."""
    permitted = (
        allowed_sections(school)
        if school is not None
        else set(SECTION_TITLES.keys())
    )

    output = []

    for code, title in SECTION_TITLES.items():
        if code not in permitted:
            continue

        rows = []

        for key, label, section, _column in LEVELS:
            if section != code:
                continue

            row = {"key": key, "label": label}

            if form is not None:
                row["m"] = form[f"{key}_m"]
                row["f"] = form[f"{key}_f"]

            if totals is not None:
                row["mt"], row["ft"], row["tt"] = totals[key]

            rows.append(row)

        output.append((code, title, rows))

    return output


def _agg_rows(school=None):
    """Return aggregate rows relevant to the school's permitted sections."""
    if school is None:
        return [(key, value[0]) for key, value in AGGREGATES.items()]

    permitted = allowed_sections(school)
    result = []

    for key, (label, _parts, _column) in AGGREGATES.items():
        if key == "k12":
            result.append((key, label))
        elif key == "es" and "ES" in permitted:
            result.append((key, label))
        elif key == "jhs" and "JHS" in permitted:
            result.append((key, label))
        elif key in {"g11", "g12", "shs"} and "SHS" in permitted:
            result.append((key, label))

    return result


def _invalid_school_type_response(request):
    messages.error(
        request,
        "This school has no valid SF4 school type assigned. "
        "Please contact your district administrator.",
    )
    return redirect("enrollment:dashboard")


@login_required
def school_entry(request, school_id):
    school = get_school_or_404(request.user, school_id)

    # Validate the school type before creating an enrollment record.
    if not allowed_sections(school):
        return _invalid_school_type_response(request)

    record = get_or_create_record(school, request.user)

    if record.status == RecordStatus.SUBMITTED:
        messages.info(
            request,
            "This record has been submitted and is locked. "
            "Ask a district administrator to reopen it.",
        )
        return redirect("enrollment:review", school_id=school.school_id)

    if request.method == "POST":
        form = EnrollmentForm(request.POST)

        if has_unauthorized_posted_values(request, school):
            messages.error(
                request,
                "Your submission contains fields not permitted for this "
                "school type. No changes were saved.",
            )
        elif form.is_valid():
            values = filter_school_values(school, form.values())
            save_values(record, values, request.user)

            log(
                request,
                "record_saved",
                record,
                district=school.district,
                school_id=school.school_id,
            )

            messages.success(request, "Draft saved.")

            if request.POST.get("action") == "review":
                return redirect(
                    "enrollment:review",
                    school_id=school.school_id,
                )

            return redirect(
                "enrollment:entry",
                school_id=school.school_id,
            )
        else:
            messages.error(request, "Please correct the highlighted fields.")
    else:
        values = filter_school_values(school, record_values(record))
        form = EnrollmentForm(initial=EnrollmentForm.initial_from(values))

    permitted_levels = allowed_level_keys(school)
    aggregate_parts = {
        key: [part for part in parts if part in permitted_levels]
        for key, (_label, parts, _column) in AGGREGATES.items()
    }

    return render(
        request,
        "enrollment/entry.html",
        {
            "school": school,
            "record": record,
            "form": form,
            "sections": _sections(form=form, school=school),
            "aggs": _agg_rows(school),
            "agg_parts": aggregate_parts,
            "year": settings.CURRENT_SCHOOL_YEAR,
            "prefilled": record_state(record) == "prefilled",
        },
    )


@login_required
def school_review(request, school_id):
    school = get_school_or_404(request.user, school_id)

    if not allowed_sections(school):
        return _invalid_school_type_response(request)

    record = get_or_create_record(school, request.user)
    values = filter_school_values(school, record_values(record))
    totals = compute_totals(values)
    state = record_state(record)

    return render(
        request,
        "enrollment/review.html",
        {
            "school": school,
            "record": record,
            "values": values,
            "totals": totals,
            "sections": _sections(totals=totals, school=school),
            "aggs": _agg_rows(school),
            "problems": submit_problems(values),
            "year": settings.CURRENT_SCHOOL_YEAR,
            "can_reopen": can_manage_district(
                request.user,
                school.district_id,
            ),
            "state_label": STATE_LABELS[state][0],
        },
    )


@login_required
def school_submit(request, school_id):
    school = get_school_or_404(request.user, school_id)

    if not allowed_sections(school):
        return _invalid_school_type_response(request)

    record = get_or_create_record(school, request.user)

    if record.status == RecordStatus.SUBMITTED:
        messages.info(request, "This record has already been submitted.")
        return redirect("enrollment:review", school_id=school.school_id)

    if request.method != "POST":
        return redirect("enrollment:review", school_id=school.school_id)

    values = filter_school_values(school, record_values(record))
    problems = submit_problems(values)

    if problems:
        messages.error(
            request,
            "Please fix the listed problems before submitting the record.",
        )
        return redirect("enrollment:review", school_id=school.school_id)

    if request.POST.get("confirm") != "yes":
        messages.error(
            request,
            "Please confirm the record before submitting it.",
        )
        return redirect("enrollment:review", school_id=school.school_id)

    submit_record(record, request.user)

    log(
        request,
        "record_submitted",
        record,
        district=school.district,
        school_id=school.school_id,
    )

    messages.success(request, "SF4 record submitted successfully.")
    return redirect("enrollment:review", school_id=school.school_id)


@require_POST
@login_required
def school_reopen(request, school_id):
    school = get_school_or_404(request.user, school_id)

    if not can_manage_district(request.user, school.district_id):
        raise PermissionDenied

    record = get_or_create_record(school, request.user)
    reopen_record(record, request.user)

    log(
        request,
        "record_reopened",
        record,
        district=school.district,
        school_id=school.school_id,
    )

    messages.success(request, "Record reopened for editing.")
    return redirect("enrollment:entry", school_id=school.school_id)


@login_required
def export_xlsx(request):
    schools = accessible_schools(request.user)
    district = request.GET.get("district", "")

    if request.user.is_system_admin and district.isdigit():
        schools = schools.filter(district_id=int(district))

    workbook = build_export(schools)

    log(
        request,
        "export",
        district=request.user.district,
        count=schools.count(),
    )

    response = HttpResponse(content_type=XLSX)
    response["Content-Disposition"] = (
        f'attachment; filename="SF4_{settings.CURRENT_SCHOOL_YEAR}.xlsx"'
    )
    workbook.save(response)

    return response
