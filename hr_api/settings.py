"""
Django settings for HR-API project.
"""

from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'apps.payroll',
    'apps.core',
    'apps.hr',
    'apps.attendance',
    'apps.recruitment',
    'storages',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hr_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'hr_api.wsgi.application'

# Database — always PostgreSQL via DATABASE_URL.
# Railway auto-injects several variable names depending on project wiring.
# We check all known forms so the app starts regardless of how the project is set up.
import dj_database_url as _dj_db_url
import os as _os


def _build_pg_url_from_components() -> str:
    from urllib.parse import quote_plus
    # Check Railway-native PG* vars first, then fall back to legacy DB_* vars
    host = (_os.environ.get('PGHOST') or _os.environ.get('RAILWAY_DB_HOST')
            or config('DB_HOST', default=''))
    user = (_os.environ.get('PGUSER')
            or config('DB_USER', default='postgres'))
    password = (_os.environ.get('PGPASSWORD')
                or config('DB_PASSWORD', default=''))
    port = (_os.environ.get('PGPORT')
            or config('DB_PORT', default='5432'))
    dbname = (_os.environ.get('PGDATABASE')
              or config('DB_NAME', default='railway'))
    if host and password:
        return f'postgresql://{user}:{quote_plus(password)}@{host}:{port}/{dbname}'
    return ''


_DATABASE_URL = (
    config('DATABASE_URL', default='')
    or _os.environ.get('DATABASE_PRIVATE_URL', '')
    or _os.environ.get('DATABASE_PUBLIC_URL', '')
    or _build_pg_url_from_components()
)
if not _DATABASE_URL:
    raise RuntimeError(
        'DATABASE_URL is not set. '
        'On Railway: link the Postgres service so DATABASE_URL is injected, '
        'or set it manually in the service Variables tab. '
        'Locally: copy .env.example to .env and fill in your database URL.'
    )

DATABASES = {'default': _dj_db_url.parse(_DATABASE_URL, conn_max_age=600)}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# Railway terminates TLS at its edge and forwards plain HTTP with an
# X-Forwarded-Proto header. Without this, request.build_absolute_uri() returns
# http:// URLs, so the approval page's fetch() is blocked as mixed content.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.payroll.authentication.ServiceKeyAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# OpenAPI / Swagger documentation (served at /api/docs/, /api/redoc/)
SPECTACULAR_SETTINGS = {
    'TITLE': 'Sheer Logic HR API',
    'DESCRIPTION': (
        'Multi-tenant HR/Payroll backend for Kenyan businesses.\n\n'
        '## Authentication\n'
        'All endpoints (except webhooks and one-tap links) require either:\n'
        '- `X-Service-Key: <key>` — service-to-service calls from the Next.js apps, or\n'
        '- `Authorization: Token <token>` — DRF token auth.\n\n'
        '## Identity & RBAC headers\n'
        'Frontend proxies forward the session user on every call:\n'
        '`X-User-Id`, `X-User-Role` (super_admin | company_admin | hr | manager | employee), '
        '`X-User-Email`, `X-Company-Id`.\n'
        'Role enforcement: payroll endpoints are **HR/admin only — never managers or '
        'employees**; other modules check `<module>.view` / `<module>.manage` grants '
        '(manage roles at `/api/rbac/`). When `RBAC_STRICT` is off, calls without role '
        'headers fall back to legacy service-key trust and are audit-logged.\n\n'
        '## Multi-tenancy\n'
        'Rows are scoped by `company_id` (pass `X-Company-Id` header or `company_id` '
        'query param on list endpoints).\n\n'
        '## Payroll lifecycle\n'
        '`draft → calculated → pending_approval → approved → processing → completed/paid`.\n'
        'Drive it via `POST /api/payroll-workflow/{run_id}/{verb}/` with verbs '
        '`submit` (generates password-protected PDF + styled Excel, opens DocuSeal '
        'submission, notifies approvers), `approve`/`reject` (records the caller\'s '
        'signature; M-of-N quorum flips the run to approved), and `mark-paid` '
        '(locks all documents immutably).\n\n'
        '## Webhooks\n'
        '- `POST /api/docuseal/webhook/` — DocuSeal signature completion\n'
        '- `POST /api/pesapal/ipn/` — PesaPal payment notifications\n'
        '- `GET|POST /api/one-tap/{token}/` — single-use approval links sent over SMS/WhatsApp/email'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/',
}

# Service key for dashboard API calls (set in environment)
HR_SERVICE_KEY = config('HR_SERVICE_KEY', default='hr-dashboard-service-key-2024')

# Celery Configuration
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# No Celery worker/Redis is deployed, so .delay() against the default
# localhost broker raises ("reconnect to result store backend") and 500s the
# request (payroll signing notifications, disbursement, IPNs). Running tasks
# eagerly executes them inline in the web process — no broker/result backend
# needed. EAGER_PROPAGATES=False keeps a task error from bubbling into (and
# re-triggering) the caller. Set CELERY_TASK_ALWAYS_EAGER=False once a real
# worker + broker are provisioned.
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = config('CELERY_TASK_EAGER_PROPAGATES', default=False, cast=bool)
CELERY_TASK_STORE_EAGER_RESULT = False

# PesaPal Configuration
PESAPAL_CONSUMER_KEY = config('PESAPAL_CONSUMER_KEY', default='')
PESAPAL_CONSUMER_SECRET = config('PESAPAL_CONSUMER_SECRET', default='')
PESAPAL_IPN_ID = config('PESAPAL_IPN_ID', default='')
PESAPAL_SANDBOX = config('PESAPAL_SANDBOX', default=True, cast=bool)

# Safaricom Daraja M-Pesa B2C Configuration
DARAJA_CONSUMER_KEY = config('DARAJA_CONSUMER_KEY', default='')
DARAJA_CONSUMER_SECRET = config('DARAJA_CONSUMER_SECRET', default='')
DARAJA_SHORTCODE = config('DARAJA_SHORTCODE', default='600998')
DARAJA_INITIATOR_NAME = config('DARAJA_INITIATOR_NAME', default='testapi')
DARAJA_INITIATOR_PASSWORD = config('DARAJA_INITIATOR_PASSWORD', default='')
DARAJA_SANDBOX = config('DARAJA_SANDBOX', default=True, cast=bool)
DARAJA_RESULT_URL = config('DARAJA_RESULT_URL', default='')
DARAJA_TIMEOUT_URL = config('DARAJA_TIMEOUT_URL', default='')

# IntaSend M-Pesa B2C Configuration (Primary for M-Pesa disbursements)
INTASEND_PUBLISHABLE_KEY = config('INTASEND_PUBLISHABLE_KEY', default='')
INTASEND_SECRET_KEY = config('INTASEND_SECRET_KEY', default='')
INTASEND_SANDBOX = config('INTASEND_SANDBOX', default=True, cast=bool)

# Africa's Talking SMS Configuration (for payment notifications)
AT_USERNAME = config('AT_USERNAME', default='sandbox')
AT_API_KEY = config('AT_API_KEY', default='')
AT_SENDER_ID = config('AT_SENDER_ID', default='')

# Demo mode - simulates payments for demonstrations
PAYMENT_DEMO_MODE = config('PAYMENT_DEMO_MODE', default=False, cast=bool)

# Disbursement is blocked until the payroll run has been e-signed by the
# employer via DocuSeal. Keep True in production (sign-then-disburse policy).
PAYROLL_REQUIRE_SIGNATURE = config('PAYROLL_REQUIRE_SIGNATURE', default=True, cast=bool)

# ---------------------------------------------------------------------------
# TimescaleDB — spatio-temporal attendance logging from the PWA.
# When TIMESCALE_ENABLED, apps.attendance models live in this database (see
# apps.attendance.router) and migration 0002 converts attendance_events into
# a hypertable. When disabled, everything stays on the default DB unchanged.
# ---------------------------------------------------------------------------
TIMESCALE_ENABLED = config('TIMESCALE_ENABLED', default=False, cast=bool)
if TIMESCALE_ENABLED:
    DATABASES['timescale'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('TIMESCALE_DB_NAME', default='hr_timeseries'),
        'USER': config('TIMESCALE_DB_USER', default='postgres'),
        'PASSWORD': config('TIMESCALE_DB_PASSWORD', default=''),
        'HOST': config('TIMESCALE_DB_HOST', default='localhost'),
        'PORT': config('TIMESCALE_DB_PORT', default='5433'),
    }
DATABASE_ROUTERS = ['apps.attendance.router.TimescaleRouter']

# Email (Resend SMTP-compatible; any SMTP provider works)
EMAIL_BACKEND = config('EMAIL_BACKEND',
                       default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.resend.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='resend')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL',
                            default='Sheer Logic HR <hr@sheerlogic.example>')

# EmailJS REST API — Railway blocks outbound SMTP ports, so when these are set
# all transactional email (payroll approvals, background checks, OTP, leave,
# etc.) is sent through EmailJS instead of Django SMTP. The PRIVATE key is
# required for server-side sends (EmailJS blocks non-browser calls otherwise).
# See apps/core/services/notifications.send_email.
EMAILJS_SERVICE_ID = config('EMAILJS_SERVICE_ID', default='')
EMAILJS_TEMPLATE_ID = config('EMAILJS_TEMPLATE_ID', default='')
EMAILJS_PUBLIC_KEY = config('EMAILJS_PUBLIC_KEY', default='')
EMAILJS_PRIVATE_KEY = config('EMAILJS_PRIVATE_KEY', default='')
EMAILJS_FROM_NAME = config('EMAILJS_FROM_NAME', default='Sheer Logic')
# Browser Origin presented to EmailJS so server-side calls pass its non-browser
# gate; must match an allowed domain if the EmailJS account restricts origins.
EMAILJS_ORIGIN = config('EMAILJS_ORIGIN',
                        default='https://hr-system-dashboard-sheerlogic.vercel.app')

# Africa's Talking WhatsApp (Chat API); falls back to SMS when unset
AT_WHATSAPP_NUMBER = config('AT_WHATSAPP_NUMBER', default='')

# DocuSeal e-signature
DOCUSEAL_BASE_URL = config('DOCUSEAL_BASE_URL', default='https://api.docuseal.com')
DOCUSEAL_API_KEY = config('DOCUSEAL_API_KEY', default='')
DOCUSEAL_WEBHOOK_SECRET = config('DOCUSEAL_WEBHOOK_SECRET', default='')
DOCUSEAL_DEMO_MODE = config('DOCUSEAL_DEMO_MODE', default=True, cast=bool)

# Smile ID facial recognition
SMILEID_PARTNER_ID = config('SMILEID_PARTNER_ID', default='')
SMILEID_API_KEY = config('SMILEID_API_KEY', default='')
SMILEID_BASE_URL = config('SMILEID_BASE_URL',
                          default='https://testapi.smileidentity.com/v1')
SMILEID_DEMO_MODE = config('SMILEID_DEMO_MODE', default=True, cast=bool)

# Public base URL used in one-tap links sent over SMS/WhatsApp
PUBLIC_API_BASE_URL = config('PUBLIC_API_BASE_URL', default='http://localhost:8000')

# GROQ — server-side AI candidate scoring
GROQ_API_KEY = config('GROQ_API_KEY', default='')
GROQ_MODEL = config('GROQ_MODEL', default='llama3-70b-8192')

# RBAC: when True, requests without role headers are denied on protected
# endpoints. Keep False until the dashboard forwards X-User-Role everywhere.
RBAC_STRICT = config('RBAC_STRICT', default=False, cast=bool)

# File storage — Supabase Storage (S3-compatible) when credentials are present.
# On Railway the filesystem is ephemeral, so payroll PDFs/Excel vanish on
# redeploy without object storage. Supabase is already in the project, so we
# reuse it. Generate S3 keys at: Supabase → Project Settings → Storage → S3 Access Keys.
_SUPABASE_URL = config('NEXT_PUBLIC_SUPABASE_URL', default='')
_SUPABASE_S3_KEY = config('SUPABASE_S3_ACCESS_KEY_ID', default='')
_SUPABASE_PROJECT_REF = _SUPABASE_URL.rstrip('/').split('//')[- 1].split('.')[0] if _SUPABASE_URL else ''

if _SUPABASE_S3_KEY and _SUPABASE_PROJECT_REF:
    _SUPABASE_S3_ENDPOINT = f'https://{_SUPABASE_PROJECT_REF}.supabase.co/storage/v1/s3'
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'endpoint_url': _SUPABASE_S3_ENDPOINT,
                'access_key': _SUPABASE_S3_KEY,
                'secret_key': config('SUPABASE_S3_SECRET_ACCESS_KEY', default=''),
                'bucket_name': config('SUPABASE_STORAGE_BUCKET', default='hr-media'),
                'region_name': 'ap-southeast-1',
                'default_acl': 'public-read',
                'file_overwrite': False,
                'object_parameters': {'CacheControl': 'max-age=86400'},
            },
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
    MEDIA_URL = f'{_SUPABASE_S3_ENDPOINT}/{config("SUPABASE_STORAGE_BUCKET", default="hr-media")}/'
else:
    # Fallback: local filesystem (dev / Railway Volume if MEDIA_ROOT is set)
    MEDIA_ROOT = config('MEDIA_ROOT', default=str(BASE_DIR / 'media'))
    MEDIA_URL = '/media/'

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=True, cast=bool)
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,https://hr-system-dashboard-sheerlogic.vercel.app',
    cast=lambda v: [s.strip() for s in v.split(',')]
)
CORS_ALLOW_CREDENTIALS = True
