from pathlib import Path
import os
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

def env_bool(name, default=False):
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)
configured_secret = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if not DEBUG and not configured_secret:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG is disabled.")
SECRET_KEY = configured_secret or "dev-only-change-me-in-production"

configured_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip()
if not DEBUG and not configured_hosts:
    raise ImproperlyConfigured("Set DJANGO_ALLOWED_HOSTS to one or more hostnames when DJANGO_DEBUG is disabled.")
ALLOWED_HOSTS = [host.strip() for host in configured_hosts.split(",") if host.strip()] if configured_hosts else ["*"]
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must include at least one hostname.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "store",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "markx.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "store.context_processors.site",
    ]},
}]

WSGI_APPLICATION = "markx.wsgi.application"

db_engine = os.environ.get("DB_ENGINE", "sqlite").strip().lower()
if db_engine in {"postgres", "postgresql"}:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", os.environ.get("POSTGRES_DB", "markx")),
        "USER": os.environ.get("DB_USER", os.environ.get("POSTGRES_USER", "")),
        "PASSWORD": os.environ.get("DB_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "")),
        "HOST": os.environ.get("DB_HOST", os.environ.get("POSTGRES_HOST", "localhost")),
        "PORT": os.environ.get("DB_PORT", os.environ.get("POSTGRES_PORT", "5432")),
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0").lower() in {"1", "true", "yes"}
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "0").lower() in {"1", "true", "yes"}
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "orders@markxcollections.pk")

LOGIN_URL = "/admin/login/"

# Store settings
MARKX = {
    "CURRENCY": "Rs. ",
    "CARD_DISCOUNT": 0.15,
    "DELIVERY_CHARGES": 200,
    "FREE_DELIVERY_OVER": 6000,
    "WHATSAPP": os.environ.get("MARKX_WHATSAPP_NUMBER", "923001234567"),
    "PAYMENT_PROVIDERS": {
        "jazzcash": {
            "enabled": env_bool("JAZZCASH_ENABLED", False),
            "merchant_id": os.environ.get("JAZZCASH_MERCHANT_ID", ""),
            "password": os.environ.get("JAZZCASH_PASSWORD", ""),
            "sandbox": env_bool("JAZZCASH_SANDBOX", True),
        },
        "easypaisa": {
            "enabled": env_bool("EASYPAYISA_ENABLED", False),
            "merchant_id": os.environ.get("EASYPAYISA_MERCHANT_ID", ""),
            "store_id": os.environ.get("EASYPAYISA_STORE_ID", ""),
            "signature": os.environ.get("EASYPAYISA_SIGNATURE", ""),
            "sandbox": env_bool("EASYPAYISA_SANDBOX", True),
        },
        "card": {
            "enabled": env_bool("CARD_PAYMENT_ENABLED", False),
            "gateway": os.environ.get("CARD_GATEWAY", ""),
            "sandbox": env_bool("CARD_SANDBOX", True),
        },
    },
    "WHATSAPP_PROVIDER": os.environ.get("WHATSAPP_PROVIDER", ""),
    "WHATSAPP_TOKEN": os.environ.get("WHATSAPP_TOKEN", ""),
    "WHATSAPP_API_URL": os.environ.get("WHATSAPP_API_URL", ""),
    "WHATSAPP_OWNER_PHONE": os.environ.get("WHATSAPP_OWNER_PHONE", ""),
    "OTP_TTL_SECONDS": int(os.environ.get("OTP_TTL_SECONDS", "300")),
    "OTP_MAX_ATTEMPTS": int(os.environ.get("OTP_MAX_ATTEMPTS", "5")),
    "OTP_RESEND_SECONDS": int(os.environ.get("OTP_RESEND_SECONDS", "60")),
    "OTP_SMS_API_URL": os.environ.get("OTP_SMS_API_URL", ""),
    "OTP_SMS_TOKEN": os.environ.get("OTP_SMS_TOKEN", ""),
    "LOYALTY_POINTS_PER_1000": int(os.environ.get("LOYALTY_POINTS_PER_1000", "1")),
    "REFERRAL_REWARD_POINTS": int(os.environ.get("REFERRAL_REWARD_POINTS", "100")),
    "ABANDONED_CART_HOURS": int(os.environ.get("ABANDONED_CART_HOURS", "24")),
    "LOYALTY_RUPEES_PER_POINT": int(os.environ.get("LOYALTY_RUPEES_PER_POINT", "1")),
}
