from django.conf import settings
from django.db import models

from .schema import LEVELS


class RecordStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"


class RecordSource(models.TextChoices):
    MANUAL = "manual", "Entered in portal"
    EXCEL_IMPORT = "excel_import", "Imported from Excel (not yet reviewed)"


class EnrollmentRecord(models.Model):
    school = models.ForeignKey("organization.School", on_delete=models.PROTECT, related_name="records")
    school_year = models.CharField(max_length=9)
    status = models.CharField(max_length=10, choices=RecordStatus.choices, default=RecordStatus.DRAFT, db_index=True)
    source = models.CharField(max_length=15, choices=RecordSource.choices, default=RecordSource.MANUAL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "school_year"], name="one_record_per_school_year")]
        indexes = [models.Index(fields=["school_year", "status"])]

    def __str__(self):
        return f"{self.school} {self.school_year}"


class EnrollmentEntry(models.Model):
    """One grade/strand row of the SF4 sheet: male and female counts (blank = not reported)."""
    record = models.ForeignKey(EnrollmentRecord, on_delete=models.CASCADE, related_name="entries")
    level = models.CharField(max_length=20, choices=[(k, l) for k, l, _s, _c in LEVELS])
    male = models.PositiveIntegerField(null=True, blank=True)
    female = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["record", "level"], name="one_entry_per_level")]
