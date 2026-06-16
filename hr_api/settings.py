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

# Database - Use SQLite for development, PostgreSQL for production
DB_ENGINE = config('DB_ENGINE', default='sqlite')

if DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='hr_api'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

    # Disable FK constraints for SQLite (data lives in Supabase, SQLite is local cache)
    from django.db.backends.signals import connection_created
    def disable_foreign_keys(sender, connection, **kwargs):
        if connection.vendor == 'sqlite':
            cursor = connection.cursor()
            cursor.execute('PRAGMA foreign_keys=OFF;')
    connection_created.connect(disable_foreign_keys)

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

# RBAC: when True, requests without role headers are denied on protected
# endpoints. Keep False until the dashboard forwards X-User-Role everywhere.
RBAC_STRICT = config('RBAC_STRICT', default=False, cast=bool)

# Generated documents (payroll PDFs/Excel)
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
