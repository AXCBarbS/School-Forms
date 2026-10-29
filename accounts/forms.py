
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
                self.add_error("password2", "Passwords do not match.")
            else:
                candidate = User(
                    email=data.get("email", ""),
                    full_name=data.get("full_name", ""),
                )
                try:
                    password_validation.validate_password(
                        password1,
                        user=candidate,
                    )
                except ValidationError as exc:
                    self.add_error("password1", exc)

        return data


class LoginForm(forms.Form):
    email = forms.EmailField(label="DepEd email address")
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password"}
        )
    )

    def get_user(self, request):
        """
        Return (user, problem).

        problem can be None, 'invalid', 'unverified', 'pending',
        'rejected', or 'suspended'.
        """
        email = normalize_email(self.cleaned_data["email"])
        password = self.cleaned_data["password"]

        user = authenticate(
            request,
            username=email,
            password=password,
        )

        if user is not None:
            return user, None

        candidate = User.objects.filter(
            email__iexact=email
        ).first()

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
    code = forms.RegexField(
        regex=r"^\d{6}$",
        max_length=6,
        min_length=6,
        label="6-digit code",
        error_messages={
            "invalid": "Enter the 6-digit code.",
        },
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "pattern": "[0-9]{6}",
                "autofocus": True,
            }
        ),
    )


class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(
        label="New DepEd email address"
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Current password",
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_email(self):
        email = validate_deped_email(
            self.cleaned_data["new_email"]
        )

        if User.objects.filter(email__iexact=email).exclude(
            pk=self.user.pk
        ).exists():
            raise ValidationError(
                "That email address cannot be used."
            )

        return email

    def clean_password(self):
        password = self.cleaned_data["password"]

        if not self.user.check_password(password):
            raise ValidationError("Incorrect password.")

        return password


class TemporaryPasswordChangeForm(forms.Form):
    """
    Form for a user who has signed in using a temporary password.
    The view must verify that the temporary password is still valid
    and clear must_change_password after a successful password change.
    """

    current_password = forms.CharField(
        label="Temporary password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password"}
        ),
    )
    new_password1 = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}
        ),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]

        if not self.user.check_password(password):
            raise ValidationError("The current password is incorrect.")

        return password

    def clean(self):
        data = super().clean()
        password1 = data.get("new_password1")
        password2 = data.get("new_password2")

        if password1 and password2:
            if password1 != password2:
                self.add_error(
                    "new_password2",
                    "The passwords do not match.",
                )
            else:
                try:
                    password_validation.validate_password(
                        password1,
                        user=self.user,
                    )
                except ValidationError as exc:
                    self.add_error("new_password1", exc)

        return data


class ActivePasswordResetForm(PasswordResetForm):
    """
    Legacy compatibility only.

    The new password-reset workflow must use administrator approval
    and temporary passwords, not password-reset emails.
    """

    def get_users(self, email):
        return (
            user
            for user in super().get_users(email)
            if user.is_fully_active
        )


class PasswordResetAuthorizationForm(forms.Form):
    """
    Legacy compatibility only.

    This authorization-code form will no longer be used by the
    administrator-approved temporary-password workflow.
    """

    email = forms.EmailField(
        label="DepEd email address",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "class": "form-control",
            }
        ),
    )

    code = forms.CharField(
        label="Authorization code",
        max_length=128,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "class": "form-control",
                "autofocus": True,
            }
        ),
    )

    new_password1 = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "form-control",
            }
        ),
    )

    new_password2 = forms.CharField(
        label="Confirm new password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "form-control",
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        data = super().clean()
        password1 = data.get("new_password1")
        password2 = data.get("new_password2")

        if password1 and password2:
            if password1 != password2:
                self.add_error(
                    "new_password2",
                    "The passwords do not match.",
                )
            elif self.user is not None:
                try:
                    password_validation.validate_password(
                        password1,
                        user=self.user,
                    )
                except ValidationError as exc:
                    self.add_error("new_password1", exc)

        return data
