from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Privacy-conscious audit trail. Never store passwords, OTPs or enrollment values here."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="audit_entries")
    actor_email = models.CharField(max_length=254, blank=True)
    action = models.CharField(max_length=60, db_index=True)
    object_type = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=60, blank=True)
    district = models.ForeignKey("organization.District", null=True, blank=True, on_delete=models.SET_NULL)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
