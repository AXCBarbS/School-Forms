
import os
import sys

import django

# Refuse to run without an explicit production database URL.
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    sys.exit(
        "STOP: DATABASE_URL is missing. "
        "No database changes were made."
    )

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sf4portal.settings")
django.setup()

from django.conf import settings
from django.db import connections, transaction
from django.db.utils import DatabaseError
from organization.models import School

# Verify Django selected PostgreSQL using DATABASE_URL.
db = connections["default"]
if db.vendor != "postgresql":
    sys.exit(
        f"STOP: Expected PostgreSQL, got {db.vendor}. "
        "No database changes were made."
    )

changes = {
    "Ampongot Barrio School": "Ampongot Elementary School",
    "Baguionas Barrio School": "Baguionas Elementary School",
    "Beleng- Belis Barrio School": "Beleng-Belis Elementary School",
    "Catiaoan Barrio School": "Catiaoan Elementary School",
    "Cayapes Barrio School": "Cayapes Elementary School",
    "Cuba Barrio School": "Cuba Elementary School",
    "Kaliwaga Barrio School": "Kaliwaga Elementary School",
    "Lao-angan Barrio School": "Lao-angan Elementary School",
    "Liblibeng Barrio School": "Liblibeng Elementary School",
    "Pakawan Barrio School": "Pakawan Elementary School",
    "Pongayan Barrio School": "Pongayan Elementary School",
    "Tadayan Barrio School": "Tadayan Elementary School",
    "Tawang Barrio School": "Tawang Elementary School",
    "Toplac Barrio School": "Toplac Elementary School",
    "Ubod Barrio School": "Ubod Elementary School",
}

# First run is preview-only. Pass --apply to make changes.
apply_changes = "--apply" in sys.argv

print("Database engine:", db.vendor)
print("Database host:", db.settings_dict.get("HOST"))
print("Database name:", db.settings_dict.get("NAME"))
print("Mode:", "APPLY" if apply_changes else "PREVIEW ONLY")

with transaction.atomic(using="default"):
    schools = {
        s.name: s
        for s in School.objects.using("default").filter(
            district_id=8,
            name__in=changes.keys(),
        )
    }

    missing = set(changes) - set(schools)
    if missing:
        raise SystemExit(
            "STOP: These original names were not found in "
            "district 8: " + ", ".join(sorted(missing))
        )

    for old, new in changes.items():
        conflict = School.objects.using("default").filter(
            district_id=8, name=new
        ).exclude(pk=schools[old].pk).exists()
        if conflict:
            raise SystemExit(
                f"STOP: Target name already exists: {new}"
            )

    print("\nPlanned changes:")
    for old, new in changes.items():
        print(f"  {old} -> {new}")

    central = School.objects.using("default").filter(
        district_id=8, pk=234, name="Kapangan Central School"
    ).exists()
    if not central:
        raise SystemExit(
            "STOP: Kapangan Central School verification failed."
        )

    if apply_changes:
        for old, new in changes.items():
            schools[old].name = new
            schools[old].save(
                using="default", update_fields=["name"]
            )
        print("\nUpdated all 15 school names.")
    else:
        print("\nPREVIEW ONLY: No names were changed.")
        # Roll back the read-only transaction explicitly.
        transaction.set_rollback(True, using="default")
