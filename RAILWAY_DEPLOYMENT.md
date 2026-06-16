# Railway Deployment — Sheer Logic HR API

Production: `https://hrmanagementapi-production-dc59.up.railway.app`
API docs once deployed: `/api/docs/` (Swagger UI) · `/api/redoc/` (ReDoc) · `/api/schema/` (OpenAPI 3 YAML)

The `Procfile` runs `python manage.py migrate --noinput` on every release. After the
**first** deploy with the new modules, run once in a Railway shell:

```bash
python manage.py seed_rbac        # 5 system roles × 32 permissions
python manage.py seed_statutory   # 2024/25 Kenyan rates + minimum wages (verify vs gazette)
```

## Environment variables

### Core Django — required
| Variable | Example / note |
|---|---|
| `SECRET_KEY` | long random string — never the dev default |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `hrmanagementapi-production-dc59.up.railway.app` |
| `CORS_ALLOW_ALL_ORIGINS` | `False` in production |
| `CORS_ALLOWED_ORIGINS` | comma-separated dashboard/PWA/careers origins (no paths) |

### Database (Railway PostgreSQL) — required
| Variable | Value |
|---|---|
| `DB_ENGINE` | `postgresql` |
| `DB_NAME` | `railway` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | `nsxUftcRRqCKhFutpdCNXnFhYWROCHXV` |
| `DB_HOST` | `thomas.proxy.rlwy.net` |
| `DB_PORT` | `14645` |

### Service auth — required
| Variable | Note |
|---|---|
| `HR_SERVICE_KEY` | must equal the frontends' `HR_SERVICE_KEY` |
| `RBAC_STRICT` | `False` until every frontend forwards `X-User-Role`; then `True` |
| `PUBLIC_API_BASE_URL` | `https://hrmanagementapi-production-dc59.up.railway.app` — used in one-tap SMS/WhatsApp links |

### Celery (background tasks + beat schedules) — required for notifications/resets/alerts
| Variable | Note |
|---|---|
| `CELERY_BROKER_URL` | Railway Redis plugin URL, e.g. `redis://default:…@…railway.internal:6379/0` |
| `CELERY_RESULT_BACKEND` | same as broker |

Add two extra Railway services off the same repo: worker `celery -A hr_api worker -l info`
and beat `celery -A hr_api beat -l info` (beat drives the per-diem reset, certificate
expiry alerts, and the <30% attendance report).

### Email (Resend SMTP-compatible) — required for approvals/share/alerts
| Variable | Value |
|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | `smtp.resend.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | `resend` |
| `EMAIL_HOST_PASSWORD` | Resend API key (`re_…`) |
| `EMAIL_USE_TLS` | `True` |
| `DEFAULT_FROM_EMAIL` | `Sheer Logic HR <hr@yourdomain.co.ke>` (verified domain in Resend) |

### Africa's Talking (SMS + WhatsApp)
| Variable | Note |
|---|---|
| `AT_USERNAME` | production AT username (`sandbox` = sandbox API) |
| `AT_API_KEY` | AT API key |
| `AT_SENDER_ID` | approved alphanumeric sender ID |
| `AT_WHATSAPP_NUMBER` | onboarded WhatsApp number; **blank = WhatsApp silently falls back to SMS** |

### Payments
| Variable | Note |
|---|---|
| `INTASEND_PUBLISHABLE_KEY` / `INTASEND_SECRET_KEY` | primary disbursement rail (M-Pesa + bank) |
| `INTASEND_SANDBOX` | `False` in production |
| `PAYMENT_DEMO_MODE` | `False` in production |
| `PESAPAL_CONSUMER_KEY` / `PESAPAL_CONSUMER_SECRET` / `PESAPAL_IPN_ID` / `PESAPAL_SANDBOX` | legacy rail, keep configured |
| `DARAJA_*` | only if direct Daraja B2C is used |

### DocuSeal (payroll e-signatures)
| Variable | Note |
|---|---|
| `DOCUSEAL_BASE_URL` | `https://api.docuseal.com` or self-hosted URL + `/api` |
| `DOCUSEAL_API_KEY` | X-Auth-Token |
| `DOCUSEAL_WEBHOOK_SECRET` | also set on the DocuSeal webhook → `POST /api/docuseal/webhook/` |
| `DOCUSEAL_DEMO_MODE` | `True` until DocuSeal account exists; `False` in production |

### Smile ID (facial check-in)
| Variable | Note |
|---|---|
| `SMILEID_PARTNER_ID` / `SMILEID_API_KEY` | from the Smile ID portal |
| `SMILEID_BASE_URL` | `https://api.smileidentity.com/v1` (prod) / `https://testapi.smileidentity.com/v1` |
| `SMILEID_DEMO_MODE` | **`True` accepts ANY selfie** — must be `False` in production |

### TimescaleDB (spatio-temporal attendance logs) — optional
| Variable | Note |
|---|---|
| `TIMESCALE_ENABLED` | `True` only when a Timescale instance exists; otherwise events store in the main DB |
| `TIMESCALE_DB_NAME` / `TIMESCALE_DB_USER` / `TIMESCALE_DB_PASSWORD` / `TIMESCALE_DB_HOST` / `TIMESCALE_DB_PORT` | e.g. Timescale Cloud or a Railway Postgres with the `timescaledb` extension |

### File storage — important caveat
`MEDIA_ROOT` defaults to `<repo>/media`. **Railway's filesystem is ephemeral** — generated
payroll PDFs/Excels vanish on redeploy. Attach a Railway **Volume** mounted at e.g.
`/data/media` and set `MEDIA_ROOT=/data/media`, or move `PayrollDocument.file` to object
storage (Supabase Storage / S3) before heavy production use.
