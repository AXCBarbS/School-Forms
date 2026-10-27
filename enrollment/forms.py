from django import forms
from django.conf import settings

from .schema import LEVELS


class EnrollmentForm(forms.Form):
    """One Male and one Female integer field per level, generated from the workbook schema."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label, _sec, _col in LEVELS:
            for suffix, who in (("m", "Male"), ("f", "Female")):
                self.fields[f"{key}_{suffix}"] = forms.IntegerField(
                    required=False, min_value=0, max_value=settings.MAX_ENROLLMENT_PER_CELL, label=f"{label} – {who}",
                    widget=forms.NumberInput(attrs={"class": "form-control form-control-sm text-end enr",
                                                    "min": 0, "max": settings.MAX_ENROLLMENT_PER_CELL,
                                                    "data-level": key, "data-sex": suffix,
                                                    "inputmode": "numeric", "aria-label": f"{label} {who}"}))

    @staticmethod
    def initial_from(values):
        return {f"{k}_{s}": v[i] for k, v in values.items() for i, s in enumerate(("m", "f"))}

    def values(self):
        return {key: (self.cleaned_data.get(f"{key}_m"), self.cleaned_data.get(f"{key}_f"))
                for key, *_ in LEVELS}
