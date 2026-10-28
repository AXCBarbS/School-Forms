from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    EnrollmentEntry,
    EnrollmentRecord,
    SF4MovementEntry,
    RecordStatus,
    RecordSource,
)
from .schema import AGGREGATES, LEVEL_KEYS, LEVEL_LABEL


def compute_totals(values):
    """values: {level: (male, female)} with None allowed. Returns {key: (M, F, T)} for every level
    and aggregate, mirroring the workbook formulas (T = M + F; aggregates sum their levels)."""
    out = {}
    for k in LEVEL_KEYS:
        m, f = values.get(k, (None, None))
        m, f = m or 0, f or 0
        out[k] = (m, f, m + f)
    for key, (_label, parts, _col) in AGGREGATES.items():
        m = sum(out[p][0] for p in parts)
        f = sum(out[p][1] for p in parts)
        out[key] = (m, f, m + f)
    return out


def record_values(record):
    vals = {k: (None, None) for k in LEVEL_KEYS}
    if record is not None:
        for e in record.entries.all():
            vals[e.level] = (e.male, e.female)
    return vals


def get_or_create_record(school, user=None):
    record, created = EnrollmentRecord.objects.get_or_create(
        school=school, school_year=settings.CURRENT_SCHOOL_YEAR,
        defaults={"created_by": user, "updated_by": user})
    if created:
        EnrollmentEntry.objects.bulk_create([EnrollmentEntry(record=record, level=k) for k in LEVEL_KEYS])
    return record


@transaction.atomic
def save_values(record, values, user):
    """values: {level: (male, female)}. Replaces all 19 levels; draft records only."""
    existing = {e.level: e for e in record.entries.select_for_update()}
    for k in LEVEL_KEYS:
        m, f = values.get(k, (None, None))
        e = existing.get(k) or EnrollmentEntry(record=record, level=k)
        e.male, e.female = m, f
        e.save()
    record.updated_by = user
    record.source = RecordSource.MANUAL
    record.save(update_fields=["updated_by", "source", "updated_at"])


def submit_problems(values):
    """Return a list of human-readable problems that block final submission."""
    problems = []
    if all(m is None and f is None for m, f in values.values()):
        problems.append("No enrollment figures have been entered.")
    for k in LEVEL_KEYS:
        m, f = values[k]
        if (m is None) != (f is None):
            problems.append(f"{LEVEL_LABEL[k]}: enter both Male and Female (use 0 if none).")
    return problems


@transaction.atomic
def submit_record(record, user):
    record.status = RecordStatus.SUBMITTED
    record.submitted_by = user
    record.submitted_at = timezone.now()
    record.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])


@transaction.atomic
def reopen_record(record, user):
    record.status = RecordStatus.DRAFT
    record.submitted_by = None
    record.submitted_at = None
    record.updated_by = user
    record.save(update_fields=["status", "submitted_by", "submitted_at", "updated_by", "updated_at"])


STATE_LABELS = {
    "not_started": ("Not Started", "secondary"),
    "prefilled": ("Pre-filled – needs review", "info"),
    "in_progress": ("In Progress", "warning"),
    "completed": ("Completed", "success"),
}


def record_state(record):
    if record is None:
        return "not_started"
    if record.status == RecordStatus.SUBMITTED:
        return "completed"
    if record.source == RecordSource.EXCEL_IMPORT:
        return "prefilled"
    return "in_progress"

MOVEMENT_CATEGORIES = ("dropout", "transferred_out", "transferred_in")
MOVEMENT_PERIODS = ("previous", "monthly")
MOVEMENT_SEXES = ("male", "female")


def movement_values(record):
    """Load saved SF4 movement figures into the enrollment form."""
    values = {}

    if record is None:
        return values

    for entry in record.movement_entries.all():
        for period in MOVEMENT_PERIODS:
            for sex in MOVEMENT_SEXES:
                field_name = f"{entry.category}_{period}_{sex}"
                values[field_name] = getattr(entry, f"{period}_{sex}")

    return values


@transaction.atomic
def save_movement_values(record, values):
    """Save all SF4 movement figures together."""
    for category in MOVEMENT_CATEGORIES:
        defaults = {}

        for period in MOVEMENT_PERIODS:
            for sex in MOVEMENT_SEXES:
                field_name = f"{category}_{period}_{sex}"
                defaults[f"{period}_{sex}"] = values.get(field_name)

        SF4MovementEntry.objects.update_or_create(
            record=record,
            category=category,
            defaults=defaults,
        )