from datetime import datetime

from django.conf import settings
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import EnrollmentRecord
from .schema import AGGREGATE_LABEL, EXPORT_ORDER, LEVEL_LABEL, SECTION_TITLES, LEVELS
from .services import compute_totals, record_state, STATE_LABELS


def build_export(schools):
    """Workbook with the same column order as the source workbook: one row per school.
    Totals are written as values calculated by the application (same rules as the workbook formulas)."""
    year = settings.CURRENT_SCHOOL_YEAR
    wb = Workbook()
    ws = wb.active
    ws.title = "Public Schools"
    head = ["No.", "School ID", "School Name", "District", "Sector", "Status"]
    sub = [""] * 6
    for kind, key in EXPORT_ORDER:
        label = LEVEL_LABEL[key] if kind == "level" else AGGREGATE_LABEL[key]
        for _ in range(3):
            head.append(label)
        sub += ["M", "F", "T"]
    ws.append([f"SF4 Enrollment {year}"])
    ws.append(head)
    ws.append(sub)
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="DDE7F3")
    for row in ws.iter_rows(min_row=1, max_row=3):
        for c in row:
            c.font = bold
            c.fill = fill
            c.alignment = Alignment(horizontal="center", wrap_text=True)
    records = {r.school_id: r for r in EnrollmentRecord.objects.filter(school__in=schools, school_year=year)
               .prefetch_related("entries")}
    grand = {}
    for n, school in enumerate(schools.order_by("district__name", "sort_order", "name"), 1):
        rec = records.get(school.id)
        vals = {e.level: (e.male, e.female) for e in rec.entries.all()} if rec else {}
        tot = compute_totals(vals)
        row = [n, school.school_id, school.name, school.district.name, school.sector,
               STATE_LABELS[record_state(rec)][0]]
        for kind, key in EXPORT_ORDER:
            m, f, t = tot[key]
            row += [m, f, t]
            g = grand.setdefault(key, [0, 0, 0])
            g[0] += m; g[1] += f; g[2] += t
        ws.append(row)
    total = ["", "", "TOTAL", "", "", ""]
    for kind, key in EXPORT_ORDER:
        total += grand.get(key, [0, 0, 0])
    ws.append(total)
    for c in ws[ws.max_row]:
        c.font = bold
    ws.freeze_panes = "D4"
    ws.column_dimensions["C"].width = 38
    for i in range(7, len(head) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 7
    ws.append([])
    ws.append([f"Exported {datetime.now():%Y-%m-%d %H:%M}. Confidential: contains school enrollment data."])
    return wb
