# Phase 7 Implementation Report — Advanced Performance Management

**Date:** 2026-06-24  
**Status:** Complete — 39/39 tests passing

---

## Overview

Phase 7 delivers advanced performance management in a new `apps/performance/` app. It builds on top of the existing basic `KpiAssignment` and `PerformanceReview` models in `apps/hr/` (unchanged) by adding: structured SMART goal-setting with progress check-ins, a competency framework, individual development plans (IDP), and 360-degree feedback.

---

## Files Delivered

### New Files

| File | Purpose |
|------|---------|
| `apps/performance/__init__.py` | Package marker |
| `apps/performance/apps.py` | `PerformanceConfig`, label='performance' |
| `apps/performance/models.py` | 8 models |
| `apps/performance/serializers.py` | 10 serializers incl. anonymous variant |
| `apps/performance/views.py` | 6 ViewSets with nested actions |
| `apps/performance/urls.py` | 6 DefaultRouter registrations |
| `apps/performance/migrations/0001_initial.py` | All 8 models |
| `apps/performance/tests/test_performance.py` | 39 tests across 7 classes |
| `apps/core/migrations/0015_performance_rbac.py` | Re-grants `performance.view/manage` |

### Modified Files

| File | Change |
|------|--------|
| `hr_api/settings.py` | Added `apps.performance` |
| `hr_api/urls.py` | Added `performance.urls` |
| `apps/core/management/commands/seed_rbac.py` | Added `'performance'` + grants to all role tiers |

---

## Models (8 total)

| Model | db_table | Purpose |
|-------|----------|---------|
| `PerformanceGoal` | `perf_goals` | SMART goal per employee; category, status, target/current values, quarterly period |
| `GoalUpdate` | `perf_goal_updates` | Check-in note on a goal; syncs `current_value` back to parent goal |
| `Competency` | `perf_competencies` | Company competency catalogue; soft-delete, is_active flag |
| `CompetencyRating` | `perf_competency_ratings` | Employee competency score per review cycle (1–5) |
| `DevelopmentPlan` | `perf_development_plans` | IDP per employee/year; soft-delete |
| `DevelopmentPlanItem` | `perf_dev_plan_items` | Line item in an IDP; type: goal/competency/course/action; UUID refs to cross-app objects |
| `FeedbackRequest` | `perf_feedback_requests` | 360 initiation; `is_anonymous` flag; lifecycle: open → closed/cancelled |
| `FeedbackResponse` | `perf_feedback_responses` | Individual 360 response; unique per reviewer+request; `submitted_at` timestamp |

---

## Endpoints

All require `performance.view` or `performance.manage`.

| URL | Description |
|-----|-------------|
| `/api/performance/goals/` | Goal CRUD; filters: employee_id, status, year |
| `/api/performance/goals/{id}/updates/` | Check-in list / create |
| `/api/performance/competencies/` | Competency catalogue CRUD; filter: active_only |
| `/api/performance/competency-ratings/` | Rating CRUD; filters: employee_id, cycle, competency_id |
| `/api/performance/development-plans/` | IDP CRUD; filter: employee_id |
| `/api/performance/development-plans/{id}/items/` | Add / list plan items |
| `/api/performance/plan-items/{id}/` | Update (mark done) / delete |
| `/api/performance/feedback-requests/` | 360 request CRUD; filter: subject_id |
| `/api/performance/feedback-requests/{id}/close/` | Close a request |
| `/api/performance/feedback-requests/{id}/respond/` | Submit a 360 response |
| `/api/performance/feedback-requests/{id}/responses/` | View responses (masked if anonymous) |

---

## Key Business Logic

**Goal progress:** `PerformanceGoalSerializer.get_progress_pct` computes from `current_value / target_value * 100` if `target_value > 0`, otherwise falls back to the latest `GoalUpdate.progress_pct`.

**Check-in sync:** `POST goals/{id}/updates/` writes a `GoalUpdate` and, if `current_value` is provided, writes it back to `PerformanceGoal.current_value` so the goal record stays current.

**Anonymity:** `FeedbackResponse.reviewer_id` is always stored (for duplicate detection). When `FeedbackRequest.is_anonymous=True`, the `responses/` action uses `FeedbackResponseAnonSerializer` which returns `reviewer_id: null`.

**Duplicate protection:** `FeedbackResponse` has a `UniqueConstraint(request, reviewer_id)` — the `respond/` action catches `IntegrityError` and returns 409.

**Cross-app references without FKs:** `DevelopmentPlanItem.goal_id`, `competency_id`, `course_id` are plain UUIDFields — they can reference objects in `apps.performance`, `apps.performance`, or `apps.lms` without DB-level foreign keys, avoiding cross-app cycles.

---

## RBAC

| Role tier | Grants |
|-----------|--------|
| super_admin, company_admin, HR roles | `performance.view` + `performance.manage` |
| Manager roles | `performance.view` |
| Employee roles | `performance.view` |

---

## Test Coverage

```
TestGoalCRUD              7 tests  — create, list, filter by employee/status, detail (with updates), update, soft-delete
TestGoalUpdate            4 tests  — add check-in, current_value sync, list, progress_pct from target
TestCompetency            5 tests  — create, list, update, soft-delete, active_only filter
TestCompetencyRating      5 tests  — create, name in response, filter by employee/cycle, list
TestDevelopmentPlan       6 tests  — create, list, detail with items, add item, mark done, soft-delete
TestFeedbackRequest       6 tests  — create, list, retrieve, close, filter by subject, response_count
TestFeedbackResponse      6 tests  — submit, duplicate 409, closed 409, anon hides reviewer, non-anon shows, avg_rating

Total: 39/39 passing
```
