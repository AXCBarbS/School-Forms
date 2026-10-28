from django.db import models


class District(models.Model):
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class School(models.Model):
    ELEMENTARY = "elementary"
    INTEGRATED = "integrated"
    NATIONAL_HIGH_SCHOOL = "national_high_school"

    SCHOOL_TYPE_CHOICES = [
        (ELEMENTARY, "Elementary"),
        (INTEGRATED, "Integrated"),
        (NATIONAL_HIGH_SCHOOL, "National High School"),
    ]

    """Master list entry. school_id is the official DepEd ID taken from the workbook."""
    school_id = models.CharField("School ID", max_length=12, unique=True)
    name = models.CharField(max_length=150)
    district = models.ForeignKey(
        District, on_delete=models.PROTECT, related_name="schools"
    )
    sector = models.CharField(max_length=20, default="Public")

    # Blank means the school still needs classification.
    # Never assume an unclassified school is Elementary.
    school_type = models.CharField(
        max_length=30,
        choices=SCHOOL_TYPE_CHOICES,
        blank=True,
        default="",
        db_index=True,
        verbose_name="School Type",
    )

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Row order in the source workbook",
    )

    class Meta:
        ordering = ["district__name", "sort_order", "name"]
        indexes = [models.Index(fields=["district", "name"])]

    def __str__(self):
        return f"{self.name} ({self.school_id})"
