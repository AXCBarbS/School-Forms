import hmac
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import OTPChallenge


class OTPError(Exception):
    pass


class OTPCooldown(OTPError):
    def __init__(self, remaining):
        super().__init__("cooldown")
        self.remaining = remaining


class OTPLimit(OTPError):
    pass


class OTPSendError(OTPError):
    pass


def _hash(salt, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{salt}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_otp(user, purpose, new_email=""):
    """Create and e-mail a fresh OTP. Enforces resend cooldown and an hourly cap."""
    now = timezone.now()
    open_qs = OTPChallenge.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True)
    last = OTPChallenge.objects.filter(user=user, purpose=purpose).order_by("-last_sent_at").first()
    if last:
        wait = settings.OTP_RESEND_COOLDOWN_SECONDS - (now - last.last_sent_at).total_seconds()
        if wait > 0:
            raise OTPCooldown(int(wait) + 1)
    sent = OTPChallenge.objects.filter(user=user, purpose=purpose, created_at__gte=now - timedelta(hours=1)).count()
    if sent >= settings.OTP_MAX_SENDS_PER_HOUR:
        raise OTPLimit()
    code = f"{secrets.randbelow(10 ** 6):06d}"
    salt = secrets.token_hex(8)
    with transaction.atomic():
        open_qs.update(consumed_at=now)  # only the newest code is valid
        challenge = OTPChallenge.objects.create(
            user=user, purpose=purpose, new_email=new_email, salt=salt, code_hash=_hash(salt, code),
            expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES), last_sent_at=now)
    target = new_email or user.email
    try:
        send_mail(
            "Your SF4 Portal verification code",
            f"Hello {user.full_name},\n\nYour verification code is {code}.\n"
            f"It expires in {settings.OTP_TTL_MINUTES} minutes. If you did not request it, ignore this message.\n",
            settings.DEFAULT_FROM_EMAIL, [target], fail_silently=False)
    except Exception as exc:  # never include the code in logs
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])
        raise OTPSendError() from exc
    return challenge


def verify_otp(user, purpose, code):
    """Return (ok, reason, challenge). reason in {ok, none, expired, locked, wrong}."""
    code = (code or "").strip()
    with transaction.atomic():
        ch = (OTPChallenge.objects.select_for_update()
              .filter(user=user, purpose=purpose, consumed_at__isnull=True).order_by("-created_at").first())
        if ch is None:
            return False, "none", None
        now = timezone.now()
        if now >= ch.expires_at:
            ch.consumed_at = now
            ch.save(update_fields=["consumed_at"])
            return False, "expired", None
        if ch.attempts >= settings.OTP_MAX_ATTEMPTS:
            ch.consumed_at = now
            ch.save(update_fields=["consumed_at"])
            return False, "locked", None
        if hmac.compare_digest(ch.code_hash, _hash(ch.salt, code)):
            ch.consumed_at = now
            ch.save(update_fields=["consumed_at"])
            return True, "ok", ch
        ch.attempts += 1
        if ch.attempts >= settings.OTP_MAX_ATTEMPTS:
            ch.consumed_at = now
            ch.save(update_fields=["attempts", "consumed_at"])
            return False, "locked", None
        ch.save(update_fields=["attempts"])
        return False, "wrong", None
