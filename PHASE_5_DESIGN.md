# Phase 5 — Executive Analytics: Design

Generated: 2026-06-24

---

## 1. Objective

Read-only aggregation layer that computes KPIs across HR, payroll, recruitment,
and CRM data. All heavy queries are cached (Django cache framework, 300s TTL).
No new database tables; only new views, services, and URLs.

---

## 2. New App: `apps/analytics/`

Label `analytics`. No models, no migrations.

---

## 3. Architecture

```
AnalyticsService.{metric}(company_id, **params)
    └─► cache.get(key)  →  hit: return cached
    └─► compute query   →  cache.set(key, result, 300)
    └─► return result
```

Each public method on `AnalyticsService` is `@staticmethod`, does one or more
aggregation queries, and is independently cacheable.

Cache key pattern: `analytics:{metric}:{company_id}:{params_hash}`

---

## 4. Metrics and Their Sources

### Overview (GET /api/analytics/overview/)
One response with all headline KPIs. Params: none.

| KPI | Source |
|-----|--------|
| total_employees | EmployeeProfile (is_deleted=False) |
| new_hires_30d | EmployeeProfile (start_date >= today-30d) |
| open_job_postings | JobPosting (status='open', is_deleted=False) |
| active_candidates | Candidate (is_deleted=False) |
| pending_leave_requests | LeaveRequest (status='pending') |
| payroll_last_run_total | PayrollRun (latest completed, total_net) |
| placements_30d | Placement (start_date >= today-30d, not cancelled) |
| active_clients | RecruitmentClient (status='active', is_deleted=False) |

### Headcount (GET /api/analytics/headcount/)
Params: `?department=`, `?period=month|quarter|year` (default year)

| Breakdown | Source |
|-----------|--------|
| by_department | EmployeeProfile GROUP BY department |
| by_employment_type | EmployeeProfile GROUP BY employment_type |
| by_worker_class | EmployeeProfile GROUP BY worker_class |
| monthly_hires | EmployeeProfile GROUP BY YEAR+MONTH(start_date) — last 12 months |
| monthly_exits | EmployeeExit GROUP BY YEAR+MONTH(last_working_day) — last 12 months |
| attrition_rate | exits_12m / avg_headcount_12m × 100 |

### Recruitment Funnel (GET /api/analytics/recruitment/)
Params: `?job_posting_id=` (optional — all postings if omitted)

| Metric | Source |
|--------|--------|
| by_stage | Candidate GROUP BY current_stage |
| by_source | Candidate GROUP BY source |
| total_applications | Candidate count |
| hired_count | Candidate(current_stage='hired') |
| conversion_rate | hired / total × 100 |
| avg_ai_score | AVG(ai_score) where not null |
| interviews_scheduled | Interview count |
| interviews_completed | Interview(status='completed') count |
| top_postings | Top 5 job postings by candidate count |

### Payroll Trend (GET /api/analytics/payroll/)
Params: `?months=12` (default 12, max 24)

| Metric | Source |
|--------|--------|
| monthly_trend | PayrollRun GROUP BY period_year+period_month — total_gross/net/deductions |
| total_spend_ytd | SUM(total_net) for current year |
| avg_salary | AVG(salary) from EmployeeProfile |
| runs | list of recent PayrollRun summaries |

### Leave Analytics (GET /api/analytics/leave/)
Params: `?year=` (default current year)

| Metric | Source |
|--------|--------|
| by_type | LeaveRequest GROUP BY leave_type COUNT+SUM(days_requested) |
| by_status | LeaveRequest GROUP BY status |
| avg_days_per_employee | total approved days / headcount |
| utilization_rate | used_days / total_days from LeaveBalance for year |

### Placement Revenue (GET /api/analytics/placements/)
Params: `?months=12`

| Metric | Source |
|--------|--------|
| monthly_placements | Placement GROUP BY YEAR+MONTH(start_date) — count + SUM(placement_fee) |
| total_fee_ytd | SUM(placement_fee) for current year, not cancelled |
| by_status | Placement GROUP BY status |
| by_client | Top 5 clients by placement count |
| total_placements | Count (not cancelled) |

---

## 5. API Endpoints

All GET. All require authentication + `X-Company-Id` header. RBAC: `analytics.view`.

| URL | Description |
|-----|-------------|
| `analytics/overview/` | All headline KPIs |
| `analytics/headcount/` | Headcount breakdown + monthly trend |
| `analytics/recruitment/` | Funnel, sources, conversion |
| `analytics/payroll/` | Monthly payroll trend |
| `analytics/leave/` | Leave utilization |
| `analytics/placements/` | Placement revenue trend |

---

## 6. RBAC

Module `analytics` → `internal_hr`, `deployed_hr`, `company_admin`, `super_admin`.

---

## 7. Caching

- Backend: `django.core.cache.cache` (default — in-memory for dev/test, Redis for prod)
- TTL: 300 seconds per cached result
- Cache key: `analytics:{endpoint}:{company_id}:{sorted_params}`
- Tests override with `CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}` to skip caching
