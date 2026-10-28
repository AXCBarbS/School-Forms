
from django import forms
from django.conf import settings

from .schema import LEVELS


MOVEMENT_CATEGORIES = [
    ("dropout", "NLPA / Dropout"),
    ("transferred_out", "Transferred Out"),
    ("transferred_in", "Transferred In"),
]


class EnrollmentForm(forms.Form):
    """Enrollment counts and SF4 movement figures."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Existing enrollment level fields
        for key, label, _sec, _col in LEVELS:
            for suffix, who in (("m", "Male"), ("f", "Female")):
                self.fields[f"{key}_{suffix}"] = forms.IntegerField(
                    required=False,
                    min_value=0,
                    max_value=settings.MAX_ENROLLMENT_PER_CELL,
                    label=f"{label} – {who}",
                    widget=forms.NumberInput(attrs={
                        "class": "form-control form-control-sm text-end enr",
                        "min": 0,
                        "max": settings.MAX_ENROLLMENT_PER_CELL,
                        "data-level": key,
                        "data-sex": suffix,
                        "inputmode": "numeric",
                        "aria-label": f"{label} {who}",
                    }),
                )

        # SF4 movement fields: previous month and current month
        for category, category_label in MOVEMENT_CATEGORIES:
            for period, period_label in (
                ("previous", "Previous Month Cumulative"),
                ("monthly", "For the Month"),
            ):
                for sex, sex_label in (
                    ("male", "Male"),
                    ("female", "Female"),
                ):
                    field_name = f"{category}_{period}_{sex}"

                    self.fields[field_name] = forms.IntegerField(
                        required=False,
                        min_value=0,
                        max_value=settings.MAX_ENROLLMENT_PER_CELL,
                        label=(
                            f"{category_label} – "
                            f"{period_label} – {sex_label}"
                        ),
                        widget=forms.NumberInput(attrs={
                            "class": (
                                "form-control form-control-sm "
                                "text-end movement-input"
                            ),
                            "min": 0,
                            "max": settings.MAX_ENROLLMENT_PER_CELL,
                            "inputmode": "numeric",
                            "aria-label": (
                                f"{category_label} "
                                f"{period_label} {sex_label}"
                            ),
                        }),
                    )

    @staticmethod
    def initial_from(values):
        # Enrollment fields contain (male, female) pairs.
        # Only iterate over known enrollment levels here.
        initial = {
            f"{key}_{sex}": values.get(key, (None, None))[index]
            for key, *_ in LEVELS
            for index, sex in enumerate(("m", "f"))
        }

        # Movement fields contain individual values, not pairs.
        for category, _label in MOVEMENT_CATEGORIES:
            for period in ("previous", "monthly"):
                for sex in ("male", "female"):
                    key = f"{category}_{period}_{sex}"
                    initial[key] = values.get(key)

        return initial

    def values(self):
        # Enrollment values are returned as (male, female) pairs.
        values = {
            key: (
                self.cleaned_data.get(f"{key}_m"),
                self.cleaned_data.get(f"{key}_f"),
            )
            for key, *_ in LEVELS
        }

        # Movement values are returned individually.
        for category, _label in MOVEMENT_CATEGORIES:
            for period in ("previous", "monthly"):
                for sex in ("male", "female"):
                    key = f"{category}_{period}_{sex}"
                    values[key] = self.cleaned_data.get(key)

        return values
