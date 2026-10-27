from django import forms
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.forms import PasswordResetForm
from django.core.exceptions import ValidationError

from organization.models import District
from .models import Approval
from .validators import normalize_email, validate_deped_email

User = get_user_model()



class RegistrationForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        strip=True,
        label="Full name",
    )
    email = forms.EmailField(label="DepEd email address")
    district = forms.ModelChoiceField(
        queryset=District.objects.none(),
        label="Assigned district",
        empty_label="Select your district",
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
        label="Password",
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
        label="Confirm password",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["district"].queryset = District.objects.filter(
            is_active=True
        )

    def clean_email(self):
        email = validate_deped_email(self.cleaned_data["email"])

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email already exists. "
                "Please sign in or contact your district administrator."
            )

        return email

    def clean(self):
        data = super().clean()
        password1 = data.get("password1")
        password2 = data.get("password2")

        if password1 and password2:
            if password1 != password2:
                self.add_error(
                    "password2",
                    "Passwords do not match.",
                )
            else:
                try:
                    password_validation.validate_password(
                        password1,
                        User(
                            email=data.get("email", ""),
                            full_name=data.get("full_name", ""),
                        ),
                    )
                except ValidationError as exc:
                    self.add_error("password1", exc)

        return data



class LoginForm(forms.Form):
    email = forms.EmailField(label="DepEd email address")
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def get_user(self, request):
        """Return (user, problem). problem in {None, 'invalid', 'unverified', 'pending', 'rejected', 'suspended'}"""
        email = normalize_email(self.cleaned_data["email"])
        password = self.cleaned_data["password"]
        user = authenticate(request, username=email, password=password)
        if user is not None:
            return user, None
        candidate = User.objects.filter(email__iexact=email).first()
        if candidate and candidate.check_password(password):
            if not candidate.is_active:
                return candidate, "suspended"
            if not candidate.email_verified:
                return candidate, "unverified"
            if candidate.approval_status == Approval.REJECTED:
                return candidate, "rejected"
            return candidate, "pending"
        return None, "invalid"


class OTPForm(forms.Form):
    code = forms.RegexField(regex=r"^\d{6}$", max_length=6, min_length=6, label="6-digit code",
                            error_messages={"invalid": "Enter the 6-digit code."},
                            widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code",
                                                          "pattern": "[0-9]{6}", "autofocus": True}))


class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(label="New DepEd email address")
    password = forms.CharField(widget=forms.PasswordInput, label="Current password")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_email(self):
        email = validate_deped_email(self.cleaned_data["new_email"])
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("That email address cannot be used.")
        return email

    def clean_password(self):
        if not self.user.check_password(self.cleaned_data["password"]):
            raise ValidationError("Incorrect password.")
        return self.cleaned_data["password"]


class ActivePasswordResetForm(PasswordResetForm):
    """Only fully active (verified + approved) users receive reset links."""
    def get_users(self, email):
        return (u for u in super().get_users(email) if u.is_fully_active)
