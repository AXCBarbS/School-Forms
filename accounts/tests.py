import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from config.testutils import PW, BaseTest, make_user
from .models import Approval, OTPChallenge, User
from .otp import OTPCooldown, OTPLimit, issue_otp, verify_otp
from .validators import validate_deped_email


class EmailDomainTests(BaseTest):
    def test_accepts_official_domain_any_case(self):
        self.assertEqual(validate_deped_email("Juan.Cruz@DepEd.gov.ph"), "juan.cruz@deped.gov.ph")

    def test_rejects_lookalikes_and_other_domains(self):
        for bad in ["x@gmail.com", "deped@gmail.com", "x@mydeped.gov.ph", "x@deped.gov.ph.evil.com",
                    "x@evildeped.gov.ph", "x@sub.deped.gov.ph", "@deped.gov.ph", "x@deped.com",
                    "x@deped.gov.ph@evil.com", "not-an-email"]:
            with self.assertRaises(ValidationError, msg=bad):
                validate_deped_email(bad)

    @override_settings(DEPED_EMAIL_DOMAINS=["deped.gov.ph", "region.deped.gov.ph"])
    def test_configured_extra_domain(self):
        self.assertEqual(validate_deped_email("a@region.deped.gov.ph"), "a@region.deped.gov.ph")



class RegistrationTests(BaseTest):
    def _post(self, **over):
        data = {
            "full_name": "New Teacher",
            "email": "new.teacher@deped.gov.ph",
            "district": self.d1.pk,
            "password1": PW,
            "password2": PW,
        }
        data.update(over)
        return self.client.post(reverse("accounts:register"), data)

    def test_register_creates_pending_verified_user_without_otp(self):
        r = self._post()

        self.assertRedirects(
            r,
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )

        u = User.objects.get(email="new.teacher@deped.gov.ph")
        self.assertTrue(u.email_verified)
        self.assertEqual(u.approval_status, Approval.PENDING)
        self.assertEqual(u.district, self.d1)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotEqual(u.password, PW)  # Password must be hashed.

    def test_password_is_never_stored_in_plaintext(self):
        self._post()

        u = User.objects.get(email="new.teacher@deped.gov.ph")
        self.assertNotEqual(u.password, PW)
        self.assertTrue(u.check_password(PW))
        self.assertEqual(OTPChallenge.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_rejects_non_deped_email(self):
        r = self._post(email="x@gmail.com")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email="x@gmail.com").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_requires_district(self):
        r = self._post(district="")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            User.objects.filter(email="new.teacher@deped.gov.ph").exists()
        )

    def test_password_confirmation_must_match(self):
        r = self._post(password2="different")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            User.objects.filter(email="new.teacher@deped.gov.ph").exists()
        )

    def test_weak_password_rejected(self):
        for weak in ("12345678", "password", "short1!"):
            r = self._post(password1=weak, password2=weak)
            self.assertEqual(r.status_code, 200, weak)

        self.assertFalse(
            User.objects.filter(email="new.teacher@deped.gov.ph").exists()
        )

    def test_duplicate_verified_email_rejected_case_insensitive(self):
        r = self._post(email="A.User@DEPED.gov.ph")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            User.objects.filter(email__iexact="a.user@deped.gov.ph").count(),
            1,
        )

    def test_reregistering_existing_email_does_not_overwrite_account(self):
        self._post()
        first = User.objects.get(email="new.teacher@deped.gov.ph")
        old_hash = first.password
        old_district = first.district

        self.client.logout()
        self._post(
            district=self.d2.pk,
            password1="An0ther-Passw0rd!z",
            password2="An0ther-Passw0rd!z",
        )

        first.refresh_from_db()
        self.assertEqual(first.password, old_hash)
        self.assertEqual(first.district, old_district)
        self.assertEqual(first.approval_status, Approval.PENDING)

    def test_district_cannot_be_unknown(self):
        r = self._post(district=99999)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            User.objects.filter(email="new.teacher@deped.gov.ph").exists()
        )




class OTPTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.u = make_user(
            "pending@deped.gov.ph",
            self.d1,
            verified=False,
            approved=False,
        )

    def code(self):
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)

    def test_correct_code_succeeds_once(self):
        issue_otp(self.u, "register")
        c = self.code()

        self.assertTrue(verify_otp(self.u, "register", c)[0])
        self.assertEqual(
            verify_otp(self.u, "register", c)[1],
            "none",
        )

    def test_wrong_code_then_lockout_after_max_attempts(self):
        issue_otp(self.u, "register")
        good = self.code()
        wrong = "000000" if good != "000000" else "111111"

        for _ in range(settings.OTP_MAX_ATTEMPTS - 1):
            self.assertEqual(
                verify_otp(self.u, "register", wrong)[1],
                "wrong",
            )

        self.assertEqual(
            verify_otp(self.u, "register", wrong)[1],
            "locked",
        )
        self.assertEqual(
            verify_otp(self.u, "register", good)[1],
            "none",
        )

    def test_expiry(self):
        issue_otp(self.u, "register")
        c = self.code()

        OTPChallenge.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.assertEqual(
            verify_otp(self.u, "register", c)[1],
            "expired",
        )

    def test_resend_cooldown_and_new_code_invalidates_old(self):
        issue_otp(self.u, "register")
        old = self.code()

        with self.assertRaises(OTPCooldown):
            issue_otp(self.u, "register")

        OTPChallenge.objects.update(
            last_sent_at=timezone.now()
            - timedelta(
                seconds=settings.OTP_RESEND_COOLDOWN_SECONDS + 1
            )
        )

        issue_otp(self.u, "register")
        new = self.code()

        if new != old:
            self.assertEqual(
                verify_otp(self.u, "register", old)[1],
                "wrong",
            )

        self.assertTrue(verify_otp(self.u, "register", new)[0])

    def test_hourly_send_cap(self):
        for _ in range(settings.OTP_MAX_SENDS_PER_HOUR):
            OTPChallenge.objects.update(
                last_sent_at=timezone.now() - timedelta(days=1)
            )
            issue_otp(self.u, "register")

        OTPChallenge.objects.update(
            last_sent_at=timezone.now() - timedelta(days=1)
        )

        with self.assertRaises(OTPLimit):
            issue_otp(self.u, "register")

    def test_registration_does_not_require_verification_session(self):
        r = self.client.get(reverse("accounts:register"))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("verify_user_id", self.client.session)

    def test_email_send_failure_does_not_affect_registration(self):
        with mock.patch(
            "accounts.otp.send_mail",
            side_effect=OSError("smtp down"),
        ):
            r = self.client.post(
                reverse("accounts:register"),
                {
                    "full_name": "X",
                    "email": "x.y@deped.gov.ph",
                    "district": self.d1.pk,
                    "password1": PW,
                    "password2": PW,
                },
            )

        self.assertEqual(r.status_code, 302)

        u = User.objects.get(email="x.y@deped.gov.ph")
        self.assertTrue(u.email_verified)
        self.assertEqual(u.approval_status, Approval.PENDING)



class LoginTests(BaseTest):
    def _login(self, email, pw=PW, **extra):
        return self.client.post(
            reverse("accounts:login"),
            {"email": email, "password": pw, **extra},
        )

    def test_approved_user_logs_in_to_dashboard(self):
        self.assertRedirects(
            self._login(self.u1.email),
            reverse("enrollment:dashboard"),
            fetch_redirect_response=False,
        )

    def test_pending_approval_cannot_login(self):
        u = make_user("p@deped.gov.ph", self.d1, approved=False)
        r = self._login(u.email)
        self.assertContains(r, "awaiting approval")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unverified_cannot_login_and_shows_error(self):
        u = make_user(
            "v@deped.gov.ph",
            self.d1,
            verified=False,
            approved=True,
        )
        r = self._login(u.email)

        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "has not verified its email")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rejected_and_suspended_cannot_login(self):
        u = make_user("r@deped.gov.ph", self.d1)
        User.objects.filter(pk=u.pk).update(
            approval_status=Approval.REJECTED
        )
        self.assertContains(self._login(u.email), "not approved")

        u2 = make_user("s@deped.gov.ph", self.d1, active=False)
        self.assertContains(self._login(u2.email), "suspended")

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

        r = self._login(self.u1.email, PW)
        self.assertContains(r, "Too many failed attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_open_redirect_blocked(self):
        r = self._login(
            self.u1.email,
            next="https://evil.example/",
        )
        self.assertRedirects(
            r,
            reverse("enrollment:dashboard"),
            fetch_redirect_response=False,
        )

        self.client.logout()
        r = self._login(self.u1.email, next="/export/")
        self.assertEqual(r["Location"], "/export/")

    def test_anonymous_redirected_from_protected_pages(self):
        for name in (
            "enrollment:dashboard",
            "enrollment:export",
            "manage:users",
            "manage:audit",
        ):
            self.assertEqual(
                self.client.get(reverse(name)).status_code,
                302,
                name,
            )

    def test_session_dies_when_user_suspended(self):
        self.login(self.u1)
        self.assertEqual(
            self.client.get(reverse("enrollment:dashboard")).status_code,
            200,
        )

        User.objects.filter(pk=self.u1.pk).update(is_active=False)
        self.assertEqual(
            self.client.get(reverse("enrollment:dashboard")).status_code,
            302,
        )

    def test_session_dies_when_approval_revoked(self):
        self.login(self.u1)
        User.objects.filter(pk=self.u1.pk).update(
            approval_status=Approval.REJECTED
        )
        self.assertEqual(
            self.client.get(reverse("enrollment:dashboard")).status_code,
            302,
        )

    def test_logout_requires_post(self):
        self.login(self.u1)
        self.assertEqual(
            self.client.get(reverse("accounts:logout")).status_code,
            405,
        )

        self.client.post(reverse("accounts:logout"))
        self.assertEqual(
            self.client.get(reverse("enrollment:dashboard")).status_code,
            302,
        )



class EmailChangeAndResetTests(BaseTest):
    def test_email_changes_only_after_otp_to_new_address(self):
        self.login(self.u1)
        self.client.post(reverse("accounts:email_change"), {"new_email": "fresh@deped.gov.ph", "password": PW})
        self.assertEqual(mail.outbox[-1].to, ["fresh@deped.gov.ph"])
        self.u1.refresh_from_db()
        self.assertEqual(self.u1.email, "a.user@deped.gov.ph")
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        self.client.post(reverse("accounts:email_change_verify"), {"code": code})
        self.u1.refresh_from_db()
        self.assertEqual(self.u1.email, "fresh@deped.gov.ph")

    def test_email_change_rejects_non_deped_wrong_password_and_taken(self):
        self.login(self.u1)
        for data in ({"new_email": "x@gmail.com", "password": PW}, {"new_email": "fresh@deped.gov.ph", "password": "bad"},
                     {"new_email": self.u2.email, "password": PW}):
            r = self.client.post(reverse("accounts:email_change"), data)
            self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_only_for_active_verified_users(self):
        make_user("unv@deped.gov.ph", self.d1, verified=False)
        self.client.post(reverse("accounts:password_reset"), {"email": "unv@deped.gov.ph"})
        self.assertEqual(len(mail.outbox), 0)
        self.client.post(reverse("accounts:password_reset"), {"email": self.u1.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)


class ModelConstraintTests(BaseTest):
    def test_non_system_admin_requires_district(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("nodistrict@deped.gov.ph", PW, full_name="X", district=None)

    def test_email_unique_case_insensitive(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.bulk_create([User(email="A.USER@deped.gov.ph", full_name="d", district=self.d1)])
