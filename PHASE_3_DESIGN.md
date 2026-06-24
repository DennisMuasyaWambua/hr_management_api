# Phase 3 — Recruitment Client CRM: Design

Generated: 2026-06-24

---

## 1. Objective

Build a B2B CRM for the staffing/recruitment agency side: track client companies,
contacts within those companies, contracts, SLAs, meeting notes, and candidate
placements. All models live in a new `apps/crm/` app isolated by `company_id`
(the agency's own company UUID).

---

## 2. New App: `apps/crm/`

Registered as `apps.crm` with label `crm`.

---

## 3. Models (single migration 0001_initial)

### RecruitmentClient
The client company that engages the agency for staffing.

| Field | Type | Notes |
|-------|------|-------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped | |
| name | CharField(200) | client company name |
| industry | CharField(100) nullable | |
| website | CharField(300) nullable | |
| location | CharField(200) nullable | |
| phone | CharField(30) nullable | |
| email | EmailField nullable | general contact email |
| account_manager_id | UUIDField nullable | internal staff user managing this account |
| status | CharField(20) choices: prospect/active/inactive/churned | default active |
| notes | TextField | |
| is_deleted | BooleanField default False | |

**db_table**: `crm_clients`  
**ordering**: `['name']`

### ClientContact
A person at a client company.

| Field | Type | Notes |
|-------|------|-------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped | |
| client | FK RecruitmentClient CASCADE | |
| full_name | CharField(200) | |
| job_title | CharField(200) nullable | |
| email | EmailField nullable | |
| phone | CharField(30) nullable | |
| linkedin_url | CharField(500) nullable | |
| is_primary | BooleanField default False | main point of contact |
| is_hiring_manager | BooleanField default False | can approve/reject hires |
| notes | TextField | |

**db_table**: `crm_client_contacts`

### ClientContract
Service agreement between agency and client.

| Field | Type | Notes |
|-------|------|-------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped | |
| client | FK RecruitmentClient CASCADE | |
| contract_type | CharField(20) choices: retained/contingency/exclusive/msa | |
| title | CharField(200) | |
| start_date | DateField | |
| end_date | DateField nullable | |
| value | DecimalField(14,2) nullable | total contract value |
| currency | CharField(3) default 'KES' | |
| fee_percentage | DecimalField(5,2) nullable | % of placed candidate salary |
| replacement_days | PositiveIntegerField default 90 | guarantee period |
| status | CharField(20) choices: draft/active/expired/terminated | default draft |
| document_url | CharField(500) nullable | |
| signed_at | DateTimeField nullable | |
| notes | TextField | |

**db_table**: `crm_contracts`

### ClientSLA
SLA metrics bound to a contract.

| Field | Type | Notes |
|-------|------|-------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped | |
| contract | FK ClientContract CASCADE related_name='slas' | |
| metric | CharField(100) | e.g. "Time to first CV" |
| target_days | PositiveIntegerField | |
| description | TextField | |

**db_table**: `crm_slas`

### ClientMeetingNote
Notes from calls/meetings with a client.

| Field | Type | Notes |
|-------|------|-------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped | |
| client | FK RecruitmentClient CASCADE | |
| meeting_type | CharField(20) choices: call/meeting/email/site_visit | default call |
| meeting_date | DateField | |
| attendees | JSONField list | list of name strings |
| summary | TextField | |
| action_items | JSONField list | list of action strings |
| author_id | UUIDField nullable | |
| author_name | CharField(200) snapshot | |

**db_table**: `crm_meeting_notes`  
**ordering**: `['-meeting_date']`

### Placement
Records a candidate placed at a client.

| Field | Type | Notes |
|-------|------|-------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped | |
| client | FK RecruitmentClient CASCADE | |
| candidate | FK recruitment.Candidate CASCADE | |
| job_posting | FK recruitment.JobPosting CASCADE nullable | |
| contact | FK ClientContact CASCADE nullable | hiring manager who approved |
| contract | FK ClientContract CASCADE nullable | which contract covers this |
| job_title | CharField(200) | role the candidate was placed into |
| start_date | DateField | |
| end_date | DateField nullable | null = permanent |
| salary | DecimalField(14,2) nullable | placed salary |
| currency | CharField(3) default 'KES' | |
| placement_fee | DecimalField(14,2) nullable | computed or manual |
| status | CharField(20) choices: offered/accepted/started/completed/cancelled | default offered |
| replacement_deadline | DateField nullable | guarantee period end |
| notes | TextField | |

**db_table**: `crm_placements`

---

## 4. API Endpoints

All under `/api/` prefix. Router-registered ViewSets.

| URL | Methods | rbac_module |
|-----|---------|-------------|
| `clients/` | GET, POST | crm |
| `clients/<uuid>/` | GET, PUT, PATCH, DELETE | crm |
| `clients/<uuid>/contacts/` | GET | crm (nested list) |
| `clients/<uuid>/contracts/` | GET | crm (nested list) |
| `clients/<uuid>/placements/` | GET | crm (nested list) |
| `clients/<uuid>/meeting-notes/` | GET | crm (nested list) |
| `client-contacts/` | GET, POST | crm |
| `client-contacts/<uuid>/` | GET, PUT, PATCH, DELETE | crm |
| `client-contracts/` | GET, POST | crm |
| `client-contracts/<uuid>/` | GET, PUT, PATCH, DELETE | crm |
| `client-contracts/<uuid>/slas/` | GET | crm (nested list) |
| `client-slas/` | GET, POST | crm |
| `client-slas/<uuid>/` | GET, PUT, PATCH, DELETE | crm |
| `client-meeting-notes/` | GET, POST | crm |
| `client-meeting-notes/<uuid>/` | GET, PUT, PATCH, DELETE | crm |
| `placements/` | GET, POST | crm |
| `placements/<uuid>/` | GET, PUT, PATCH, DELETE | crm |

---

## 5. RBAC

| Module | Grants |
|--------|--------|
| `crm` | internal_hr, deployed_hr, company_admin, super_admin |

---

## 6. Filters

- `clients/`: `?status=`, `?account_manager_id=`, `?q=` (name/email/industry search)
- `client-contacts/`: `?client_id=`, `?is_hiring_manager=`
- `client-contracts/`: `?client_id=`, `?status=`
- `client-meeting-notes/`: `?client_id=`
- `placements/`: `?client_id=`, `?status=`, `?candidate_id=`
