
import csv
from pathlib import Path

from django.db import transaction
from organization.models import School

CSV_PATH = Path("school_classification.csv")
ALLOWED_TYPES = {
    "elementary",
    "integrated",
    "national_high_school",
}

with CSV_PATH.open(encoding="utf-8-sig", newline="") as file:
    rows = list(csv.DictReader(file))

if len(rows) != 430:
    raise ValueError(f"Expected 430 rows, found {len(rows)}")

ids = [row["School ID"].strip() for row in rows]

if len(ids) != len(set(ids)):
    raise ValueError("Duplicate School IDs found.")

for row in rows:
    school_type = row["School Type"].strip().lower()
    if school_type not in ALLOWED_TYPES:
        raise ValueError(
            f"Invalid school type for {row['School ID']}: {school_type!r}"
        )

schools = {
    school.school_id: school
    for school in School.objects.filter(school_id__in=ids)
}

if set(ids) != set(schools):
    raise ValueError("CSV School IDs do not match the database.")

for row in rows:
    school = schools[row["School ID"].strip()]
    if row["School Name"].strip().casefold() != school.name.strip().casefold():
        raise ValueError(f"School name mismatch: {school.school_id}")

updated = 0

with transaction.atomic():
    for row in rows:
        school = schools[row["School ID"].strip()]
        new_type = row["School Type"].strip().lower()

        if school.school_type != new_type:
            school.school_type = new_type
            school.save(update_fields=["school_type"])
            updated += 1

print("Import successful.")
print("Rows validated:", len(rows))
print("Records updated:", updated)

for school_type in sorted(ALLOWED_TYPES):
    print(
        f"{school_type}:",
        School.objects.filter(school_type=school_type).count(),
    )
