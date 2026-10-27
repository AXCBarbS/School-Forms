from django.core.management.base import BaseCommand, CommandError

from organization.importer import apply_import, parse_workbook, reconcile


class Command(BaseCommand):
    help = "Import districts and schools (and optionally enrollment baselines) from the consolidated SF4 workbook."

    def add_arguments(self, p):
        p.add_argument("path")
        p.add_argument("--with-enrollment", action="store_true",
                       help="Also load the workbook's figures as pre-filled DRAFT records for review.")
        p.add_argument("--dry-run", action="store_true", help="Validate and report only; write nothing.")
        p.add_argument("--reconcile", action="store_true", help="Compare database totals with the workbook.")

    def handle(self, *a, **o):
        try:
            parsed = parse_workbook(o["path"])
        except FileNotFoundError:
            raise CommandError("File not found: " + o["path"])
        rep = apply_import(parsed, with_enrollment=o["with_enrollment"], dry_run=o["dry_run"])
        for k, v in rep.items():
            if k in ("errors", "warnings", "schools_moved"):
                continue
            self.stdout.write(f"{k}: {v}")
        for k in ("errors", "warnings", "schools_moved"):
            self.stdout.write(f"{k}: {len(rep[k])}")
            for line in rep[k][:50]:
                self.stdout.write("   - " + line)
        if rep["errors"]:
            raise CommandError("Import rejected: fix the errors above. Nothing was written.")
        if o["reconcile"] and o["with_enrollment"] and not o["dry_run"]:
            rec = reconcile(parsed)
            self.stdout.write(f"reconciled rows: {rec['rows_checked']}; mismatches: {len(rec['mismatches'])}")
            for line in rec["mismatches"][:100]:
                self.stdout.write("   - " + line)
            for name, t in rec["district_totals"]:
                self.stdout.write(f"   {name}: database K-12 total {t['db']} / workbook {t['wb']}")
