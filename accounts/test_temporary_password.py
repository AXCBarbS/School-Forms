
"""Tests for administrator-issued temporary passwords."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from config.testutils import BaseTest, PW, make_user


class TemporaryPasswordChangeTests(BaseTest):
    NEW_PASSWORD = "N3w-Strong-Passw0rd!y"

    def setUp(self):
        super().setUp()

        self.user = make_user(
            "temporary.user@deped.gov.ph",
            self.d1,
        )
        self.user.must_change_password = True
        self.user.temporary_password_expires_at = (
            timezone.now() + timedelta(hours=24)
        )
        self.user.save(
            update_fields=[
                "must_change_password",
                "temporary_password_expires_at",
            ]
        )

        self.change_url = reverse(
            "accounts:temporary_password_change"
        )

    def test_temporary_password_user_is_redirected_to_change_page(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": self.user.email,
                "password": PW,
            },
        )

        self.assertRedirects(
            response,
            self.change_url,
            fetch_redirect_response=False,
        )

        self.assertIn("_auth_user_id", self.client.session)

    def test_temporary_password_user_cannot_access_dashboard(self):
        self.login(self.user)

        response = self.client.get(
            reverse("enrollment:dashboard")
        )

        self.assertRedirects(
            response,
            self.change_url,
            fetch_redirect_response=False,
        )

    def test_incorrect_current_password_is_rejected(self):
        self.login(self.user)

        response = self.client.post(
            self.change_url,
            {
                "current_password": "Incorrect-Temporary-Pass1!",
                "new_password1": self.NEW_PASSWORD,
                "new_password2": self.NEW_PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "The current password is incorrect.",
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)
        self.assertTrue(self.user.check_password(PW))

    def test_mismatched_new_passwords_are_rejected(self):
        self.login(self.user)

        response = self.client.post(
            self.change_url,
            {
                "current_password": PW,
                "new_password1": self.NEW_PASSWORD,
                "new_password2": "Different-Password1!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "The passwords do not match.",
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)
        self.assertTrue(self.user.check_password(PW))

    def test_expired_temporary_password_logs_user_out(self):
        self.user.temporary_password_expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.user.save(
            update_fields=["temporary_password_expires_at"]
        )

        self.login(self.user)

        response = self.client.get(self.change_url)

        self.assertRedirects(
            response,
            reverse("accounts:password_reset"),
            fetch_redirect_response=False,
        )

        self.assertNotIn("_auth_user_id", self.client.session)

        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)

    def test_successful_password_change_clears_temporary_password_flag(self):
        self.login(self.user)

        response = self.client.post(
            self.change_url,
            {
                "current_password": PW,
                "new_password1": self.NEW_PASSWORD,
                "new_password2": self.NEW_PASSWORD,
            },
        )

        self.assertRedirects(
            response,
            reverse("enrollment:dashboard"),
            fetch_redirect_response=False,
        )

        self.user.refresh_from_db()

        self.assertFalse(self.user.must_change_password)
        self.assertIsNone(
            self.user.temporary_password_expires_at
        )
        self.assertTrue(
            self.user.check_password(self.NEW_PASSWORD)
        )
        self.assertFalse(self.user.check_password(PW))

        # The user should remain authenticated after changing the password.
        self.assertIn("_auth_user_id", self.client.session)

        dashboard_response = self.client.get(
            reverse("enrollment:dashboard")
        )
        self.assertEqual(dashboard_response.status_code, 200)
