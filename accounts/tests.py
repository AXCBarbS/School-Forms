from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse

from config.testutils import PW, BaseTest, make_user
from .models import Approval, PasswordResetRequest, User
from .validators import validate_deped_email


class EmailDomainTests(BaseTest):
    def test_accepts_official_domain_any_case(self):
        self.assertEqual(
            validate_deped_email("Juan.Cruz@DepEd.gov.ph"),
            "juan.cruz@deped.gov.ph",
        )

    def test_rejects_lookalikes_and_other_domains(self):
        bad_emails = [
            "x@gmail.com",
            "deped@gmail.com",
            "x@mydeped.gov.ph",
            "x@deped.gov.ph.evil.com",
            "x@evildeped.gov.ph",
            "x@sub.deped.gov.ph",
            "@deped.gov.ph",
            "x@deped.com",
            "x@deped.gov.ph@evil.com",
            "not-an-email",
        ]

        for email in bad_emails:
            with self.subTest(email=email):
                with self.assertRaises(ValidationError):
                    validate_deped_email(email)

    @override_settings(
        DEPED_EMAIL_DOMAINS=[
            "deped.gov.ph",
            "region.deped.gov.ph",
        ]
    )
    def test_configured_extra_domain(self):
        self.assertEqual(
            validate_deped_email("a@region.deped.gov.ph"),
            "a@region.deped.gov.ph",
        )


class RegistrationTests(BaseTest):
    def _post(self, **overrides):
        data = {
            "full_name": "New Teacher",
            "email": "new.teacher@deped.gov.ph",
            "district": self.d1.pk,
            "password1": PW,
            "password2": PW,
        }
        data.update(overrides)

        return self.client.post(
            reverse("accounts:register"),
            data,
        )

    def test_register_creates_pending_verified_user_without_otp(self):
        response = self._post()

        self.assertRedirects(
            response,
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )

        user = User.objects.get(
            email="new.teacher@deped.gov.ph",
        )

        self.assertTrue(user.email_verified)
        self.assertEqual(
            user.approval_status,
            Approval.PENDING,
        )
        self.assertEqual(user.district, self.d1)
        self.assertNotEqual(user.password, PW)
        self.assertTrue(user.check_password(PW))
        self.assertEqual(len(mail.outbox), 0)

    def test_password_is_never_stored_in_plaintext(self):
        self._post()

        user = User.objects.get(
            email="new.teacher@deped.gov.ph",
        )

        self.assertNotEqual(user.password, PW)
        self.assertTrue(user.check_password(PW))
        self.assertEqual(len(mail.outbox), 0)

    def test_rejects_non_deped_email(self):
        response = self._post(email="x@gmail.com")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(email="x@gmail.com").exists()
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_requires_district(self):
        response = self._post(district="")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(
                email="new.teacher@deped.gov.ph"
            ).exists()
        )

    def test_password_confirmation_must_match(self):
        response = self._post(password2="different")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(
                email="new.teacher@deped.gov.ph"
            ).exists()
        )

    def test_weak_password_rejected(self):
        for weak_password in (
            "12345678",
            "password",
            "short1!",
        ):
            with self.subTest(password=weak_password):
                response = self._post(
                    password1=weak_password,
                    password2=weak_password,
                )
                self.assertEqual(response.status_code, 200)

        self.assertFalse(
            User.objects.filter(
                email="new.teacher@deped.gov.ph"
            ).exists()
        )

    def test_duplicate_verified_email_rejected_case_insensitive(self):
        response = self._post(
            email="A.User@DEPED.gov.ph",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            User.objects.filter(
                email__iexact="a.user@deped.gov.ph"
            ).count(),
            1,
        )

    def test_reregistering_existing_email_does_not_overwrite_account(self):
        self._post()

        original = User.objects.get(
            email="new.teacher@deped.gov.ph",
        )
        original_password_hash = original.password
        original_district = original.district

        self.client.logout()

        self._post(
            district=self.d2.pk,
            password1="An0ther-Passw0rd!z",
            password2="An0ther-Passw0rd!z",
        )

        original.refresh_from_db()

        self.assertEqual(
            original.password,
            original_password_hash,
        )
        self.assertEqual(
            original.district,
            original_district,
        )
        self.assertEqual(
            original.approval_status,
            Approval.PENDING,
        )

    def test_district_cannot_be_unknown(self):
        response = self._post(district=99999)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(
                email="new.teacher@deped.gov.ph"
            ).exists()
        )


class LoginTests(BaseTest):
    def _login(self, email, password=PW, **extra):
        return self.client.post(
            reverse("accounts:login"),
            {
                "email": email,
                "password": password,
                **extra,
            },
        )

    def test_approved_user_logs_in_to_dashboard(self):
        response = self._login(self.u1.email)

        self.assertRedirects(
            response,
            reverse("enrollment:dashboard"),
            fetch_redirect_response=False,
        )

    def test_pending_approval_cannot_login(self):
        user = make_user(
            "p@deped.gov.ph",
            self.d1,
            approved=False,
        )

        response = self._login(user.email)

        self.assertContains(response, "awaiting approval")
        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_unverified_cannot_login_and_shows_error(self):
        user = make_user(
            "v@deped.gov.ph",
            self.d1,
            verified=False,
            approved=True,
        )

        response = self._login(user.email)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "has not verified its email",
        )
        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_rejected_and_suspended_cannot_login(self):
        rejected_user = make_user(
            "r@deped.gov.ph",
            self.d1,
        )

        User.objects.filter(
            pk=rejected_user.pk,
        ).update(
            approval_status=Approval.REJECTED,
        )

        self.assertContains(
            self._login(rejected_user.email),
            "not approved",
        )

        suspended_user = make_user(
            "s@deped.gov.ph",
            self.d1,
            active=False,
        )

        self.assertContains(
            self._login(suspended_user.email),
            "suspended",
        )

    def test_wrong_password_generic_message(self):
        self.assertContains(
            self._login(self.u1.email, "nope"),
            "Invalid email or password",
        )

        self.assertContains(
            self._login("ghost@deped.gov.ph"),
            "Invalid email or password",
        )

    def test_login_throttle_after_repeated_failures(self):
        for _ in range(settings.LOGIN_MAX_FAILURES):
            self._login(self.u1.email, "bad")

        response = self._login(self.u1.email, PW)

        self.assertContains(
            response,
            "Too many failed attempts",
        )
        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_open_redirect_blocked(self):
        response = self._login(
            self.u1.email,
            next="https://evil.example/",
        )

        self.assertRedirects(
            response,
            reverse("enrollment:dashboard"),
            fetch_redirect_response=False,
        )

        self.client.logout()

        response = self._login(
            self.u1.email,
            next="/export/",
        )

        self.assertEqual(
            response["Location"],
            "/export/",
        )

    def test_anonymous_redirected_from_protected_pages(self):
        protected_pages = (
            "enrollment:dashboard",
            "enrollment:export",
            "manage:users",
            "manage:audit",
        )

        for url_name in protected_pages:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302)

    def test_session_dies_when_user_suspended(self):
        self.login(self.u1)

        self.assertEqual(
            self.client.get(
                reverse("enrollment:dashboard")
            ).status_code,
            200,
        )

        User.objects.filter(
            pk=self.u1.pk,
        ).update(is_active=False)

        self.assertEqual(
            self.client.get(
                reverse("enrollment:dashboard")
            ).status_code,
            302,
        )

    def test_session_dies_when_approval_revoked(self):
        self.login(self.u1)

        User.objects.filter(
            pk=self.u1.pk,
        ).update(
            approval_status=Approval.REJECTED,
        )

        self.assertEqual(
            self.client.get(
                reverse("enrollment:dashboard")
            ).status_code,
            302,
        )

    def test_logout_requires_post(self):
        self.login(self.u1)

        self.assertEqual(
            self.client.get(
                reverse("accounts:logout")
            ).status_code,
            405,
        )

        self.client.post(reverse("accounts:logout"))

        self.assertEqual(
            self.client.get(
                reverse("enrollment:dashboard")
            ).status_code,
            302,
        )


class EmailChangeAndResetTests(BaseTest):
    def test_email_change_rejects_non_deped_wrong_password_and_taken(self):
        self.login(self.u1)

        invalid_requests = (
            {
                "new_email": "x@gmail.com",
                "password": PW,
            },
            {
                "new_email": "fresh@deped.gov.ph",
                "password": "bad",
            },
            {
                "new_email": self.u2.email,
                "password": PW,
            },
        )

        for data in invalid_requests:
            with self.subTest(data=data):
                response = self.client.post(
                    reverse("accounts:email_change"),
                    data,
                )
                self.assertEqual(response.status_code, 200)

        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_only_for_active_verified_users(self):
        unverified_user = make_user(
            "unv@deped.gov.ph",
            self.d1,
            verified=False,
        )

        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": unverified_user.email},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        self.assertFalse(
            PasswordResetRequest.objects.filter(
                user=unverified_user,
            ).exists()
        )

        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.u1.email},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        reset_request = PasswordResetRequest.objects.get(
            user=self.u1,
        )

        self.assertEqual(
            reset_request.status,
            PasswordResetRequest.Status.PENDING,
        )

        self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.u1.email},
        )

        self.assertEqual(
            PasswordResetRequest.objects.filter(
                user=self.u1,
                status=PasswordResetRequest.Status.PENDING,
            ).count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_cannot_create_password_reset_request(self):
        inactive_user = make_user(
            "inactive@deped.gov.ph",
            self.d1,
            active=False,
        )

        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": inactive_user.email},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        self.assertFalse(
            PasswordResetRequest.objects.filter(
                user=inactive_user,
            ).exists()
        )

    def test_unknown_email_does_not_create_password_reset_request(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "unknown@deped.gov.ph"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PasswordResetRequest.objects.count(), 0)


class ModelConstraintTests(BaseTest):
    def test_non_system_admin_requires_district(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    "nodistrict@deped.gov.ph",
                    PW,
                    full_name="X",
                    district=None,
                )

    def test_email_unique_case_insensitive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.bulk_create(
                    [
                        User(
                            email="A.USER@deped.gov.ph",
                            full_name="Duplicate",
                            district=self.d1,
                        )
                    ]
                )