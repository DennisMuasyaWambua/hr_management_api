# Phase 7 Design — Advanced Performance Management

**Date:** 2026-06-24

---

## Scope

Build `apps/performance/` on top of the existing `KpiAssignment` and `PerformanceReview` models in `apps/hr/` (which are not changed). Phase 7 adds:

1. **SMART Goals** — structured goal-setting with progress check-ins
2. **Competency Framework** — company-level competency catalogue + per-employee ratings
3. **Individual Development Plans (IDP)** — link goals, competency gaps, and LMS courses
4. **360-Degree Feedback** — request → multi-reviewer response → summary

---

## Data Model

### 1. PerformanceGoal

```python
class PerformanceGoal(TenantStamped):
    STATUS = [('draft','Draft'),('active','Active'),('completed','Completed'),
              ('cancelled','Cancelled')]
    CATEGORY = [('okr','OKR'),('kpi','KPI'),('development','Development'),('other','Other')]

    employee_id    UUIDField(db_index=True)
    title          CharField(200)
    description    TextField(blank=True)
    category       CharField(20, choices=CATEGORY, default='okr')
    status         CharField(20, choices=STATUS, default='draft')
    target_value   FloatField(null=True)          # measurable metric
    current_value  FloatField(default=0)
    due_date       DateField(null=True)
    period_year    IntegerField()
    period_quarter IntegerField(null=True, blank=True)  # Q1-Q4 or null for annual
    owner_id       UUIDField(null=True)            # manager who set the goal
    weight         FloatField(default=1.0)         # for weighted avg scoring
    is_deleted     BooleanField(default=False)

    db_table = 'perf_goals'
    indexes = [Index(fields=['company_id','employee_id'], name='pg_co_emp_idx')]
```

### 2. GoalUpdate (check-ins)

```python
class GoalUpdate(TenantStamped):
    goal           ForeignKey(PerformanceGoal, related_name='updates')
    progress_pct   FloatField()          # 0-100
    current_value  FloatField(null=True)
    note           TextField(blank=True)
    author_id      UUIDField(null=True)

    db_table = 'perf_goal_updates'
    ordering = ['-created_at']
```

### 3. Competency

```python
class Competency(TenantStamped):
    CATEGORY = [('technical','Technical'),('leadership','Leadership'),
                ('behavioural','Behavioural'),('functional','Functional')]

    name        CharField(200)
    description TextField(blank=True)
    category    CharField(20, choices=CATEGORY, default='technical')
    is_active   BooleanField(default=True)
    is_deleted  BooleanField(default=False)

    db_table = 'perf_competencies'
    unique_together = [('company_id', 'name')]
```

### 4. CompetencyRating

```python
class CompetencyRating(TenantStamped):
    employee_id  UUIDField(db_index=True)
    competency   ForeignKey(Competency)
    rating       PositiveSmallIntegerField()  # 1-5
    review_cycle CharField(20)               # e.g. '2026-H1'
    rated_by     UUIDField(null=True)
    notes        TextField(blank=True)

    db_table = 'perf_competency_ratings'
    unique_together = [('employee_id', 'competency', 'review_cycle')]
    indexes = [Index(fields=['company_id','employee_id'], name='cr_co_emp_idx')]
```

### 5. DevelopmentPlan

```python
class DevelopmentPlan(TenantStamped):
    STATUS = [('draft','Draft'),('active','Active'),('completed','Completed')]

    employee_id  UUIDField(db_index=True)
    title        CharField(200)
    period_year  IntegerField()
    status       CharField(20, choices=STATUS, default='draft')
    summary      TextField(blank=True)
    owner_id     UUIDField(null=True)      # HR or manager who approved
    is_deleted   BooleanField(default=False)

    db_table = 'perf_development_plans'
```

### 6. DevelopmentPlanItem

```python
class DevelopmentPlanItem(TenantStamped):
    TYPE = [('goal','Goal'),('competency','Competency Gap'),
            ('course','LMS Course'),('action','Action Item')]

    plan         ForeignKey(DevelopmentPlan, related_name='items')
    item_type    CharField(20, choices=TYPE)
    title        CharField(200)
    description  TextField(blank=True)
    due_date     DateField(null=True)
    is_done      BooleanField(default=False)
    # optional references
    goal_id      UUIDField(null=True)          # PerformanceGoal.id
    competency_id UUIDField(null=True)         # Competency.id
    course_id    UUIDField(null=True)          # lms.Course.id
    order        PositiveIntegerField(default=0)

    db_table = 'perf_dev_plan_items'
```

### 7. FeedbackRequest (360)

```python
class FeedbackRequest(TenantStamped):
    STATUS = [('open','Open'),('closed','Closed'),('cancelled','Cancelled')]

    subject_id    UUIDField(db_index=True)   # employee being reviewed
    requester_id  UUIDField()                 # usually the subject or their manager
    review_cycle  CharField(20)              # e.g. '2026-H1'
    due_date      DateField(null=True)
    status        CharField(20, choices=STATUS, default='open')
    is_anonymous  BooleanField(default=True)
    is_deleted    BooleanField(default=False)

    db_table = 'perf_feedback_requests'
    indexes = [Index(fields=['company_id','subject_id'], name='fr_co_sub_idx')]
```

### 8. FeedbackResponse

```python
class FeedbackResponse(TenantStamped):
    request      ForeignKey(FeedbackRequest, related_name='responses')
    reviewer_id  UUIDField()               # masked if is_anonymous
    overall_rating  PositiveSmallIntegerField()  # 1-5
    strengths    TextField(blank=True)
    improvements TextField(blank=True)
    answers      JSONField(default=dict)   # free-form Q&A
    submitted_at DateTimeField(null=True)

    db_table = 'perf_feedback_responses'
    unique_together = [('request', 'reviewer_id')]
```

---

## Endpoints

All require `performance.view` or `performance.manage`.

### Goals
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/performance/goals/` | List / create goals (filter: employee_id, year, status) |
| GET/PATCH/DELETE | `/api/performance/goals/{id}/` | Detail / update / soft-delete |
| GET/POST | `/api/performance/goals/{id}/updates/` | Check-ins for a goal |

### Competencies
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/performance/competencies/` | Competency catalogue |
| GET/PATCH/DELETE | `/api/performance/competencies/{id}/` | Detail |
| GET/POST | `/api/performance/competency-ratings/` | Rate employee on competency |
| GET | `/api/performance/competency-ratings/?employee_id=&cycle=` | Filter ratings |

### Development Plans
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/performance/development-plans/` | List / create |
| GET/PATCH/DELETE | `/api/performance/development-plans/{id}/` | Detail (includes items) |
| GET/POST | `/api/performance/development-plans/{id}/items/` | Add items |
| PATCH/DELETE | `/api/performance/plan-items/{id}/` | Update / remove item |

### 360 Feedback
| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/performance/feedback-requests/` | List / create requests |
| GET/PATCH | `/api/performance/feedback-requests/{id}/` | Detail / close/cancel |
| POST | `/api/performance/feedback-requests/{id}/respond/` | Submit response |
| GET | `/api/performance/feedback-requests/{id}/responses/` | View responses (manager only) |

---

## RBAC

Module: `performance` (already exists in seed_rbac `_HR_GRANTS`). New migration `0015_performance_rbac` grants it explicitly to catch any ordering gaps. Employees get `performance.view` to see their own goals/plans (scoping enforced at queryset level).

---

## Key Design Decisions

1. **UUID references, not FKs** — `goal_id`, `competency_id`, `course_id` in `DevelopmentPlanItem` are UUIDs, not DB foreign keys. This avoids cross-app FK cycles and allows items to reference resources that don't exist yet.

2. **Anonymity** — `FeedbackResponse.reviewer_id` is always stored (for deduplication), but serializer omits it when `request.is_anonymous=True`.

3. **No change to hr/KpiAssignment** — existing KPI workflow is left intact. `PerformanceGoal` is additive.

4. **Competency unique per company** — `unique_together = [('company_id', 'name')]` on `Competency`; DRF gets `UniqueTogetherValidator` but `company_id` is always in context (set server-side) so this is safe.

---

## Migration Plan

1. `apps/performance/migrations/0001_initial.py` — all 8 models
2. `apps/core/migrations/0015_performance_rbac.py` — re-grant `performance.view/manage`

---

## Test Plan (target ≥ 50 tests)

| Class | Count | Coverage |
|-------|-------|----------|
| TestGoalCRUD | 7 | create, list (filter by status), detail, update, soft-delete, updates |
| TestGoalUpdate | 4 | add check-in, progress updated, list |
| TestCompetency | 5 | CRUD, list active only |
| TestCompetencyRating | 5 | rate, list by employee, duplicate cycle rejected |
| TestDevelopmentPlan | 6 | create, list, detail with items, add item, mark done, soft-delete |
| TestFeedbackRequest | 6 | create, list, retrieve, close, respond, response list |
| TestFeedbackResponse | 5 | submit, duplicate reviewer rejected, anon hides reviewer, overall stats |
| TestRBAC | 4 | 401 without auth, 403 wrong module |
