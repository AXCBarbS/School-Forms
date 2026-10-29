
"""Tests for the System Admin password-reset approval workflow."""

from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from accounts.models import Approval, PasswordResetRequest, Role
from audit.models import AuditLog
from config.testutils import BaseTest, make_user


class PasswordResetApprovalTests(BaseTest):
    def setUp(self):
        super().setUp()

        self.target = make_user(
            "reset.target@deped.gov.ph",
            self.d1,
        )
        self.reset_request = PasswordResetRequest.objects.create(
            user=self.target,
        )
        self.url = reverse(
            "manage:password_reset_request_action",
            args=[self.reset_request.pk, "approve"],
        )
        self.login(self.sysadmin)

    def create_request(self, user):
        return PasswordResetRequest.objects.create(user=user)

    def test_approval_generates_temporary_password(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Temporary Password Generated")

        self.target.refresh_from_db()
        self.reset_request.refresh_from_db()

        self.assertTrue(self.target.must_change_password)
        self.assertIsNotNone(
            self.target.temporary_password_expires_at
        )
        self.assertTrue(
            self.target.temporary_password_expires_at
            > timezone.now()
        )
        self.assertTrue(
            self.target.temporary_password_expires_at
            <= timezone.now() + timedelta(hours=24, minutes=1)
        )
        self.assertEqual(
            self.reset_request.status,
            PasswordResetRequest.Status.APPROVED,
        )
        self.assertEqual(
            self.reset_request.reviewed_by,
            self.sysadmin,
        )

        # The temporary password is displayed once and is not stored
        # in plaintext in the database.
        self.assertNotEqual(
            self.target.password,
            response.content.decode().split(
                '<div class="password">'
            )[1].split("</div>")[0],
        )

    def test_approval_page_disables_caching(self):
        response = self.client.post(self.url)

        self.assertEqual(
            response["Cache-Control"],
            "no-store, no-cache, must-revalidate, max-age=0",
        )
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_rejection_does_not_change_password(self):
        original_password_hash = self.target.password
        original_flag = self.target.must_change_password

        reject_url = reverse(
            "manage:password_reset_request_action",
            args=[self.reset_request.pk, "reject"],
        )
        response = self.client.post(reject_url)

        self.assertRedirects(
            response,
            reverse("manage:password_reset_requests"),
        )

        self.target.refresh_from_db()
        self.reset_request.refresh_from_db()

        self.assertEqual(
            self.target.password,
            original_password_hash,
        )
        self.assertEqual(
            self.target.must_change_password,
            original_flag,
        )
        self.assertEqual(
            self.reset_request.status,
            PasswordResetRequest.Status.REJECTED,
        )
        self.assertEqual(
            self.reset_request.reviewed_by,
            self.sysadmin,
        )

    def test_inactive_account_cannot_be_approved(self):
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        original_password_hash = self.target.password

        response = self.client.post(self.url, follow=True)

        self.assertContains(
            response,
            "This account is not active, verified, and approved",
        )

        self.target.refresh_from_db()
        self.reset_request.refresh_from_db()

        self.assertEqual(
            self.target.password,
            original_password_hash,
        )
        self.assertFalse(self.target.must_change_password)
        self.assertEqual(
            self.reset_request.status,
            PasswordResetRequest.Status.PENDING,
        )

    def test_unapproved_account_cannot_be_approved(self):
        self.target.approval_status = Approval.PENDING
        self.target.save(update_fields=["approval_status"])
        original_password_hash = self.target.password

        response = self.client.post(self.url, follow=True)

        self.assertContains(
            response,
            "This account is not active, verified, and approved",
        )

        self.target.refresh_from_db()
        self.reset_request.refresh_from_db()

        self.assertEqual(
            self.target.password,
            original_password_hash,
        )
        self.assertFalse(self.target.must_change_password)
        self.assertEqual(
            self.reset_request.status,
            PasswordResetRequest.Status.PENDING,
        )

    def test_already_reviewed_request_cannot_be_approved_again(self):
        first_response = self.client.post(self.url)
        self.assertEqual(first_response.status_code, 200)

        self.target.refresh_from_db()
        first_password_hash = self.target.password
        first_expiry = self.target.temporary_password_expires_at

        second_response = self.client.post(self.url, follow=True)

        self.assertContains(
            second_response,
            "This request has already been reviewed.",
        )

        self.target.refresh_from_db()

        self.assertEqual(self.target.password, first_password_hash)
        self.assertEqual(
            self.target.temporary_password_expires_at,
            first_expiry,
        )

    def test_regular_user_cannot_approve_request(self):
        self.client.logout()
        self.login(self.u1)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)

        self.target.refresh_from_db()
        self.reset_request.refresh_from_db()

        self.assertFalse(self.target.must_change_password)
        self.assertEqual(
            self.reset_request.status,
            PasswordResetRequest.Status.PENDING,
        )

    def test_district_admin_cannot_approve_request(self):
        self.client.logout()
        self.login(self.admin1)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)

        self.target.refresh_from_db()
        self.reset_request.refresh_from_db()

        self.assertFalse(self.target.must_change_password)
        self.assertEqual(
            self.reset_request.status,
            PasswordResetRequest.Status.PENDING,
        )

    def test_approval_is_post_only(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

        self.reset_request.refresh_from_db()
        self.assertEqual(
            self.reset_request.status,
            PasswordResetRequest.Status.PENDING,
        )

    def test_audit_log_does_not_contain_temporary_password(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)

        temporary_password = (
            response.content.decode()
            .split('<div class="password">')[1]
            .split("</div>")[0]
        )

        audit_entry = AuditLog.objects.get(
            action="password_reset_request_approved"
        )

        self.assertNotIn(
            temporary_password,
            str(audit_entry.details),
        )
