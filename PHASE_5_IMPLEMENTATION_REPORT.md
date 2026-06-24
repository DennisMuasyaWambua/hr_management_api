# Phase 5 Implementation Report — Executive Analytics

**Date:** 2026-06-24  
**Status:** Complete — 36/36 tests passing

---

## Overview

Phase 5 delivers a cached, read-only analytics API that aggregates data across all ERP modules into executive-level dashboards. Six endpoint groups cover headcount, recruitment funnels, payroll trends, leave utilisation, and placement fees.

---

## Files Delivered

### New Files

| File | Purpose |
|------|---------|
| `apps/analytics/__init__.py` | Package marker |
| `apps/analytics/apps.py` | AppConfig (`label='analytics'`) |
| `apps/analytics/services.py` | `AnalyticsService` — 6 static methods, 5-minute cache |
| `apps/analytics/views.py` | 6 `APIView` subclasses, all `rbac_module='analytics'` |
| `apps/analytics/urls.py` | 6 URL patterns under `analytics/` |
| `apps/analytics/tests/__init__.py` | Package marker |
| `apps/analytics/tests/test_analytics.py` | 36 tests across 6 test classes |
| `apps/core/migrations/0013_analytics_rbac.py` | Grants `analytics.view/manage` to HR and admin roles |

### Modified Files

| File | Change |
|------|--------|
| `hr_api/settings.py` | Added `apps.analytics` to `INSTALLED_APPS` |
| `hr_api/urls.py` | Added `path('api/', include('apps.analytics.urls'))` |
| `apps/core/management/commands/seed_rbac.py` | Added `'analytics'` to `MODULES` list |
| `apps/hr/urls.py` | Removed shadowing routes (`analytics/recruitment/`, `analytics/payroll/`) that conflicted with the new app |

---

## Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/analytics/overview/` | 8-KPI dashboard snapshot |
| GET | `/api/analytics/headcount/` | Headcount by dept/type/class + monthly hires/exits + attrition |
| GET | `/api/analytics/recruitment/` | Funnel, conversion rate, top postings, interviews |
| GET | `/api/analytics/payroll/` | Monthly trend, YTD spend, average salary |
| GET | `/api/analytics/leave/` | By type/status, approved days, utilisation rate |
| GET | `/api/analytics/placements/` | Monthly placements, fee YTD, top clients |

All endpoints require `analytics.view` permission. Query params: `months` (payroll, placements), `year` (leave), `job_posting_id` (recruitment).

---

## Architecture

**Caching:** All service methods cache responses for 300 seconds using Django's cache framework. Cache keys are MD5-hashed from `company_id` + query params to namespace per-tenant. Tests inject `DummyCache` via `@override_settings(CACHES=NO_CACHE)` to bypass caching.

**Date aggregation (SQLite):** Monthly grouping uses `.extra(select={'yr': "strftime('%%Y', field)", 'mo': "strftime('%%m', field)"})` — the double-percent escaping is required because Django's `extra()` processes the string through Python's `%`-formatting before passing it to the DB.

**Company isolation:** Every service method receives `company_id` from `request_company_id(request)` (reads `X-Company-Id` header) and filters all querysets by it.

---

## Issues Resolved

1. **URL shadowing** — `apps/hr/urls.py` had pre-existing routes for `analytics/recruitment/` and `analytics/payroll/` (from `apps/hr/analytics.py`) that were matched before the new analytics app's routes. Removed the two shadowing entries from `apps/hr/urls.py`; kept `analytics/workforce/` which is not duplicated.

2. **`PayrollRun.run_by` NOT NULL** — Test fixture was missing `run_by=uuid.uuid4()`.

3. **`EmployeeProfile.user_id` NOT NULL** — Test helper `_employee()` was missing `user_id=uuid.uuid4()`.

---

## Test Coverage

```
TestOverviewView          7 tests  — KPI keys, counts, 30-day hires, active clients
TestHeadcountView         5 tests  — keys, by-department, total, monthly structure
TestRecruitmentView       7 tests  — keys, applications, hired, conversion rate, source, filter
TestPayrollAnalyticsView  5 tests  — keys, monthly trend, months param, avg salary
TestLeaveAnalyticsView    5 tests  — keys, by-type, year param, utilisation rate
TestPlacementAnalyticsView 7 tests — keys, total count, cancelled excluded, fee YTD, months param, top clients

Total: 36/36 passing
```
