# Production Readiness Report

**Date:** 2026-06-24  
**Auditor:** Repository-wide automated + manual analysis  
**Verdict:** ⚠️ NOT PRODUCTION-READY — 9 blocking gaps, 14 high-priority gaps

---

## Executive Summary

The API has a sophisticated, well-architected feature set with real-world integrations (PesaPal, IntaSend, Smile ID, DocuSeal, Africa's Talking). However, the following critical gaps block a safe production deployment: **zero automated tests on the three most critical modules** (payroll, HR, core), **all payment/identity integrations default to sandbox/demo mode**, and **several security defaults are unsafe** unless environment variables are explicitly set.

---

## 1. Critical Blockers (must fix before go-live)

### B-1 — Zero test coverage on revenue-critical modules

| Module | Test files | Test methods | Risk |
|--------|-----------|--------------|------|
| `apps/payroll` | 0 | 0 | CRITICAL — payroll calculations, disbursements, approvals |
| `apps/hr` | 0 | 0 | CRITICAL — leave, exits, compliance, disciplinary |
| `apps/core` | 0 | 0 | CRITICAL — RBAC, auth, OTP, audit log |
| `apps/attendance` | 0 | 0 | HIGH — geofencing, check-in, face verification |

The PAYE/NSSF/NHIF/Housing Levy calculation engine (`KenyanTaxCalculator`) has **zero automated verification**. A single-line regression could silently underpay all employees. The payroll approval workflow (multi-quorum, DocuSeal integration) has never been regression-tested.

**Fix:** Write a minimum of 50 tests for `apps/payroll` covering tax bracket boundaries, approval quorum logic, and disbursement status transitions before any production payroll run.

---

### B-2 — All external integrations default to sandbox/demo

Every integration defaults safe-but-wrong for production:

| Integration | Setting | Default |
|-------------|---------|---------|
| PesaPal (payment) | `PESAPAL_SANDBOX` | `True` |
| Safaricom Daraja | `DARAJA_SANDBOX` | `True` |
| IntaSend (M-Pesa primary) | `INTASEND_SANDBOX` | `True` |
| Smile ID (face ID) | `SMILEID_DEMO_MODE` | `True` |
| DocuSeal (e-signatures) | `DOCUSEAL_DEMO_MODE` | `True` |
| Payment system | `PAYMENT_DEMO_MODE` | `False` ✓ |

**Risk:** If environment variables are not set correctly on deployment, live payroll runs will silently use sandbox payment endpoints — employees will not be paid, with no error raised.

**Fix:** Require explicit `PESAPAL_SANDBOX=false` (or equivalent) in production deployment checklist. Add a startup check that raises `ImproperlyConfigured` if sandbox flags are True when `DEBUG=False`.

---

### B-3 — RBAC_STRICT defaults to False

```python
RBAC_STRICT = config('RBAC_STRICT', default=False, cast=bool)
```

When `RBAC_STRICT=False`, requests without an `X-User-Role` header **bypass all module permission checks** and are allowed through with a `rbac.legacy_access` audit log entry. This was designed for backwards compatibility during migration but is unsafe in production.

**Risk:** Any caller that omits the role header (misconfigured service, external attacker with a valid token) gets full access to every module.

**Fix:** Set `RBAC_STRICT=true` in the production environment. Audit all API callers to ensure they send the role header. Remove the legacy bypass once confirmed.

---

### B-4 — Celery defaults to eager (synchronous) mode

```python
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=True, cast=bool)
```

All async tasks execute synchronously in the request/response cycle when this is True. Any task that sends SMS/email, generates a PDF, or calls a payment API will block the request thread.

**Risk:** Payroll disbursement to 500 employees (each making an M-Pesa API call) would block the request for minutes or time out. Notification sending on leave approval would slow every approval response.

**Fix:** Set `CELERY_TASK_ALWAYS_EAGER=false` in production. Ensure the docker-compose Celery worker is deployed.

---

### B-5 — File storage is ephemeral without explicit configuration

```
DEFAULT_FILE_STORAGE: local filesystem (/app/media/) unless SUPABASE_S3_ACCESS_KEY_ID is set
```

Railway's filesystem is ephemeral — files written locally are lost on redeploy. Payroll PDFs, signed documents, and profile pictures would vanish.

**Risk:** `PayrollDocument.file` (PDF + Excel reports), `EmployeeProfile.profile_picture_url`, and uploaded receipts are silently lost on every deployment.

**Fix:** Configure `SUPABASE_S3_ACCESS_KEY_ID` and `SUPABASE_S3_PROJECT_REF` in production to force S3 storage. Alternatively use a mounted Railway volume (persistent disk).

---

### B-6 — Email backend defaults to console

```python
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
```

OTP codes, leave approvals, payroll one-tap links, and onboarding emails are printed to stdout in production if `EMAIL_BACKEND` is not set.

**Risk:** Users receive no emails; OTP login fails silently; one-tap payroll approval links are never delivered.

**Fix:** Set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and configure Resend SMTP credentials. The EmailJS fallback is already implemented for SMTP port blocks.

---

### B-7 — No health check endpoint

No `/health/` or `/api/health/` endpoint exists. Railway, load balancers, and uptime monitors have nothing to ping.

**Fix:** Add a 2-line view returning `{"status": "ok"}` at `/health/`. Register it without authentication. Takes 10 minutes.

---

### B-8 — Admin URL defaults to `/admin/`

```python
ADMIN_URL = config('ADMIN_URL', default='admin/')
```

The default is widely known. Automated scanners actively probe `/admin/` for Django admin panels.

**Fix:** Set `ADMIN_URL` to a random UUID slug in production env var (e.g., `ADMIN_URL=a3f7c1e4b2d9/`).

---

### B-9 — No CI/CD pipeline

No `.github/workflows/`, `.gitlab-ci.yml`, or equivalent exists. Deployments are manual via Railway's Procfile. There is no automated test run on push, no linting gate, and no staging environment validation.

**Risk:** Any developer can push breaking code directly to production without any automated gate.

**Fix:** Add a GitHub Actions workflow: `pytest → collect static → docker build → deploy to Railway staging`. Minimum: `python manage.py test --verbosity=0` on every PR.

---

## 2. High-Priority Gaps (fix within 2 weeks of go-live)

### H-1 — No API versioning
All endpoints are `/api/<resource>/` with no version prefix. A breaking change requires coordinating all clients simultaneously.

**Fix:** Add `/api/v1/` prefix now while the client count is small.

### H-2 — Token authentication only (no JWT expiry)
DRF `Token` is a static UUID that never expires. A stolen token grants permanent access until manually revoked.

**Fix:** Replace with `djangorestframework-simplejwt` (access token 15min, refresh token 7d). Or add a token rotation endpoint.

### H-3 — No global 500 error logging
Unhandled exceptions produce Django's default 500 page (or empty JSON). No Sentry/Rollbar/Datadog integration captures stacktraces.

**Fix:** Add `sentry-sdk[django]` with DSN from env var. One line in `settings.py`.

### H-4 — ALLOWED_HOSTS defaults to localhost
```python
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', ...)
```
Production hostname must be explicitly listed or Django will return 400 on every request.

**Fix:** Set `ALLOWED_HOSTS=api.sheerlogic.example,*.railway.app` in Railway env vars.

### H-5 — No database connection pooling beyond conn_max_age
`conn_max_age=600` reuses connections within the same process but doesn't pool across workers. Under load with gunicorn workers + Celery workers, connection count can exhaust PostgreSQL's `max_connections`.

**Fix:** Add `pgbouncer` sidecar or configure `django-db-connection-pool`.

### H-6 — No rate limiting on data mutation endpoints
Rate limiting covers auth endpoints (login: 10/min, OTP: 5/min) and global (anon: 200/hr, user: 2000/hr), but no per-resource rate limiting. A user can submit 2000 payroll runs per hour.

**Fix:** Add `ScopedRateThrottle` with custom scopes on payroll submission, disbursement, and bulk employee endpoints.

### H-7 — Audit log gaps
`ServiceAuditLog` is called manually at key points (payroll, RBAC) but not systematically on all data mutations. Regulatory environments (Kenya's Data Protection Act) may require full CRUD audit trails.

**Fix:** Add a Django signal or DRF middleware that logs every POST/PUT/PATCH/DELETE to `ServiceAuditLog`.

### H-8 — No backup strategy documented
No backup schedule, retention policy, or disaster recovery runbook is in the repo.

### H-9 — Timescale DB conditionally supported but not tested
`TimescaleRouter` and hypertable migration exist but there are zero tests validating the dual-database routing. The migration has `IF NOT EXISTS` guards but has never been run in CI.

### H-10 — Secret rotation not supported
`ServiceKeyAuthentication` uses a static `X-Service-Key` from environment. No rotation mechanism or key versioning exists.

### H-11 — PesaPal IPN endpoint has no signature verification
`@csrf_exempt` PesaPalIPNWebhook accepts any POST. PesaPal's IPN should be verified against HMAC signature.

**Fix:** Validate `X-PesaPal-Signature` header on every IPN.

### H-12 — DocuSeal webhook has no signature verification
`/api/docuseal/webhook/` — no `DOCUSEAL_WEBHOOK_SECRET` verification found in the webhook handler.

### H-13 — Face descriptor stored as JSON in PostgreSQL
`EmployeeProfile.face_descriptor` is a JSONField storing a 128-float array. This is correct for small deployments but will become a full-table-scan bottleneck at scale (pgvector would allow indexed ANN search).

### H-14 — No soft-delete on core auth models
`AppUser` has `is_deleted=True` but Django's `auth.User` (FK via `auth_user`) is hard-deleted. Deleting a Django user cascades and breaks foreign keys in `ServiceAuditLog`, `PayrollApproval`, etc.

**Fix:** Override `AppUser.delete()` to set `is_active=False` on both models instead of hard-deleting.

---

## 3. Current Strengths (do not regress)

| Strength | Detail |
|----------|--------|
| Multi-tenancy | `company_id` isolation on every model; enforced at queryset level |
| RBAC depth | 11 role types, per-module grants, payroll hard rule, deployed-role scoping |
| Kenyan compliance | PAYE bands, NSSF tiers, NHIF/SHIF, Housing Levy, minimum wage alerts |
| Payment integrations | PesaPal + IntaSend + Daraja (3 M-Pesa paths) |
| Audit trail | `ServiceAuditLog` at payroll, approval, RBAC change points |
| Security headers | HSTS, X-Frame-Options, content type nosniff (non-DEBUG) |
| One-tap approvals | Single-use tokenized links for offline approvers |
| Document generation | Password-protected PDF + XLSX payroll documents |
| Notification multi-channel | Email, SMS, WhatsApp (Africa's Talking) |
| OpenAPI | Swagger + ReDoc at /api/docs/ and /api/redoc/ |

---

## 4. Production Deployment Checklist (minimum)

```
[ ] Set RBAC_STRICT=true
[ ] Set DEBUG=false
[ ] Set SECRET_KEY to 50+ char random string
[ ] Set ALLOWED_HOSTS to production hostname
[ ] Set DATABASE_URL to production PostgreSQL
[ ] Set REDIS_CACHE_URL to production Redis
[ ] Set ADMIN_URL to random UUID path
[ ] Set EMAIL_BACKEND + Resend SMTP credentials
[ ] Set PESAPAL_SANDBOX=false (or INTASEND/DARAJA)
[ ] Set CELERY_TASK_ALWAYS_EAGER=false
[ ] Set SUPABASE_S3_* for file storage
[ ] Set AT_USERNAME and AT_API_KEY for notifications
[ ] Write payroll module tests (B-1)
[ ] Add /health/ endpoint (B-7)
[ ] Configure error tracking (Sentry)
[ ] Set up CI/CD pipeline
```
