"""Shared fixtures for tests."""
from django.test import TestCase
from django.core.cache import cache

from accounts.models import Approval, Role, User
from organization.models import District, School

PW = "Str0ng-Passw0rd!x"


def make_user(email, district, role=Role.USER, approved=True, verified=True, active=True, name="Test User"):
    return User.objects.create_user(
        email, PW, full_name=name, district=district, role=role, email_verified=verified,
        approval_status=Approval.APPROVED if approved else Approval.PENDING, is_active=active)


class BaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.d1 = District.objects.create(name="Atok")
        self.d2 = District.objects.create(name="Bakun")
        self.s1a = School.objects.create(school_id="100001", name="Adoyunan ES", district=self.d1, sort_order=1)
        self.s1b = School.objects.create(school_id="100002", name="Bilis ES", district=self.d1, sort_order=2)
        self.s2a = School.objects.create(school_id="200001", name="Ampusongan ES", district=self.d2, sort_order=1)
        self.u1 = make_user("a.user@deped.gov.ph", self.d1)
        self.u2 = make_user("b.user@deped.gov.ph", self.d2)
        self.admin1 = make_user("a.admin@deped.gov.ph", self.d1, Role.DISTRICT_ADMIN)
        self.admin2 = make_user("b.admin@deped.gov.ph", self.d2, Role.DISTRICT_ADMIN)
        self.sysadmin = User.objects.create_superuser("root@deped.gov.ph", PW, full_name="Root")

    def login(self, user):
        self.client.logout()
        ok = self.client.login(username=user.email, password=PW)
        self.assertTrue(ok, f"could not log in {user.email}")
