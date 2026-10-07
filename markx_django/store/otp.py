import hmac
import json
import secrets
from datetime import timedelta
from urllib import request, error

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import OTPChallenge


def _digest(code):
    return salted_hmac("store.cod.otp", code, secret=settings.SECRET_KEY, algorithm="sha256").hexdigest()


def send_cod_otp(phone):
    config = settings.MARKX
    if not config.get("OTP_SMS_API_URL") or not config.get("OTP_SMS_TOKEN"):
        return False, "SMS OTP delivery is not configured."
    latest = OTPChallenge.objects.filter(phone=phone).order_by("-created").first()
    cooldown = int(config.get("OTP_RESEND_SECONDS", 60))
    if latest and (timezone.now() - latest.created).total_seconds() < cooldown:
        return False, "Please wait before requesting another code."
    code = f"{secrets.randbelow(1_000_000):06d}"
    OTPChallenge.objects.create(
        phone=phone, code_digest=_digest(code),
        expires_at=timezone.now() + timedelta(seconds=int(config.get("OTP_TTL_SECONDS", 300))),
    )
    payload = json.dumps({"to": phone, "message": f"Your MarkX verification code is {code}."}).encode()
    req = request.Request(config["OTP_SMS_API_URL"], data=payload, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {config['OTP_SMS_TOKEN']}"})
    try:
        with request.urlopen(req, timeout=10) as response:
            if response.status < 300:
                return True, "Verification code sent."
    except (error.URLError, TimeoutError, ValueError):
        pass
    return False, "Could not deliver the verification code. Try again later."


def verify_cod_otp(phone, code):
    challenge = OTPChallenge.objects.filter(phone=phone, verified_at__isnull=True).order_by("-created").first()
    if not challenge or challenge.expires_at <= timezone.now():
        return False
    if challenge.attempts >= int(settings.MARKX.get("OTP_MAX_ATTEMPTS", 5)):
        return False
    challenge.attempts += 1
    challenge.save(update_fields=["attempts"])
    if not hmac.compare_digest(challenge.code_digest, _digest(code.strip())):
        return False
    challenge.verified_at = timezone.now()
    challenge.save(update_fields=["verified_at"])
    return True
