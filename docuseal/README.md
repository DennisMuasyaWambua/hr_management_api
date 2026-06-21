# Self-hosting DocuSeal for HR-API

DocuSeal is a **separate e-signature server** (a Rails app). The Django HR-API
backend only contains a *client* (`apps/core/services/docuseal.py`) that calls
it over HTTP. Until a real DocuSeal server is running and wired in, the backend
stays in **demo mode** (`DOCUSEAL_DEMO_MODE=True`) — it returns stub submissions
and **sends no emails**. That is the current state.

This folder gives you a ready-to-run DocuSeal instance and the exact env wiring.

---

## Option A — Railway (recommended, same project as the API)

1. **New service → Deploy a Docker image**: `docuseal/docuseal:latest`.
2. **Add a Postgres** plugin/service and copy its connection string.
3. Set these variables on the DocuSeal service:
   - `DATABASE_URL` = the Postgres connection string
   - `SECRET_KEY_BASE` = `openssl rand -hex 64`
   - `HOST` = the public domain Railway assigns the service (e.g. `docuseal-production.up.railway.app`)
   - SMTP vars (`SMTP_ADDRESS`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`) so it can email signers
4. Generate a public domain for the service and open it.
5. Create the first admin account, then go to **Settings → API** and copy the **API token**.

## Option B — Any Docker host / VPS

```bash
cd docuseal
export SECRET_KEY_BASE=$(openssl rand -hex 64)
export POSTGRES_PASSWORD=$(openssl rand -hex 16)
export DOCUSEAL_HOST=docuseal.yourdomain.com   # put it behind TLS
docker compose up -d
```
Then open the host, create the admin user, and grab the API token from **Settings → API**.

---

## Wire it into the HR-API (Django) service

Set these on the **HR-API** Railway service (NOT the DocuSeal one), then redeploy:

```
DOCUSEAL_DEMO_MODE=False
DOCUSEAL_BASE_URL=https://<your-docuseal-domain>/api
DOCUSEAL_API_KEY=<the API token from DocuSeal → Settings → API>
DOCUSEAL_WEBHOOK_SECRET=<any long random string>
```

## Configure the return webhook (signed PDF → Sheer Logic)

In DocuSeal → **Settings → Webhooks**, add:

- URL: `https://hrmanagementapi-production-dc59.up.railway.app/api/docuseal/webhook/`
- Events: `form.completed`, `submission.completed`
- Secret: the same value as `DOCUSEAL_WEBHOOK_SECRET`

This is what records each signature back onto the payroll run (and background
checks), flips the run to `approved`, and stores the signed PDF.

---

## Verify

After both services are redeployed, a payroll "Send for signing" creates a real
submission (id will NOT start with `demo-`) and emails the configured signer.
You can confirm the mode by checking a generated document's
`docuseal_submission_id` via `GET /api/payroll-documents/?payroll_run_id=<id>`.
