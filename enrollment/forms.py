
from django import forms
from django.conf import settings

from .schema import LEVELS


MOVEMENT_CATEGORIES = [
    ("dropout", "NLPA / Dropout"),
    ("transferred_out", "Transferred Out"),
    ("transferred_in", "Transferred In"),
]

MOVEMENT_PERIODS = [
    ("previous", "A — Cumulative as of Previous Month"),
    ("monthly", "B — For the Month"),
]


class EnrollmentForm(forms.Form):
    """Enrollment counts and per-level SF4 movement figures."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for key, label, _section, _column in LEVELS:
            for suffix, sex_label in (("m", "Male"), ("f", "Female")):
                self.fields[f"{key}_{suffix}"] = forms.IntegerField(
                    required=False,
                    min_value=0,
                    max_value=settings.MAX_ENROLLMENT_PER_CELL,
                    label=f"{label} – {sex_label}",
                    widget=forms.NumberInput(attrs={
                        "class": "form-control form-control-sm text-end enr",
                        "min": 0,
                        "max": settings.MAX_ENROLLMENT_PER_CELL,
                        "data-level": key,
                        "data-sex": suffix,
                        "inputmode": "numeric",
                        "aria-label": f"{label} {sex_label}",
                    }),
                )

        for level, level_label, _section, _column in LEVELS:
            for category, category_label in MOVEMENT_CATEGORIES:
                for period, period_label in MOVEMENT_PERIODS:
                    for sex, sex_label in (
                        ("male", "Male"),
                        ("female", "Female"),
                    ):
                        field_name = (
                            f"{level}_{category}_{period}_{sex}"
                        )
                        self.fields[field_name] = forms.IntegerField(
                            required=False,
                            min_value=0,
                            max_value=settings.MAX_ENROLLMENT_PER_CELL,
                            label=(
                                f"{level_label} – {category_label} – "
                                f"{period_label} – {sex_label}"
                            ),
                            widget=forms.NumberInput(attrs={
                                "class": (
                                    "form-control form-control-sm "
                                    "movement-input"
                                ),
                                "min": 0,
                                "max": settings.MAX_ENROLLMENT_PER_CELL,
                                "inputmode": "numeric",
                                "data-level": level,
                                "data-category": category,
                                "data-period": period,
                                "data-sex": sex,
                            }),
                        )

    @staticmethod
    def initial_from(values):
        initial = {}

        for key, *_ in LEVELS:
            male, female = values.get(key, (None, None))
            initial[f"{key}_m"] = male
            initial[f"{key}_f"] = female

        for level, *_ in LEVELS:
            for category, _ in MOVEMENT_CATEGORIES:
                for period, _ in MOVEMENT_PERIODS:
                    for sex in ("male", "female"):
                        key = f"{level}_{category}_{period}_{sex}"
                        initial[key] = values.get(key)

        return initial

    def values(self):
        values = {
            key: (
                self.cleaned_data.get(f"{key}_m"),
                self.cleaned_data.get(f"{key}_f"),
            )
            for key, *_ in LEVELS
        }

        for level, *_ in LEVELS:
            for category, _ in MOVEMENT_CATEGORIES:
                for period, _ in MOVEMENT_PERIODS:
                    for sex in ("male", "female"):
                        key = f"{level}_{category}_{period}_{sex}"
                        values[key] = self.cleaned_data.get(key)

        return values
