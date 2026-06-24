# Phase 1 — Workflow Automation Engine: Implementation Report

Completed: 2026-06-24

---

## Status: ✅ Complete — 100/100 tests passing

---

## What Was Built

### New App: `apps/workflows/`

| File | Purpose |
|------|---------|
| `models.py` | WorkflowDefinition, WorkflowExecution, WorkflowExecutionLog, WorkflowTask |
| `conditions.py` | ConditionEvaluator with 14 operators |
| `executors.py` | ExecutorRegistry + 8 action executors |
| `engine.py` | WorkflowEngine.fire() — central dispatch |
| `signals.py` | Signal handler functions (connected in apps.py.ready()) |
| `apps.py` | AppConfig with signal wiring and executor registration |
| `templates.py` | 5 built-in workflow templates |
| `serializers.py` | DRF serializers for all 4 models |
| `views.py` | 10 API views (list/create/detail/activate/deactivate/complete) |
| `urls.py` | 10 URL patterns under `/api/workflows/` |
| `migrations/0001_initial.py` | Creates 4 tables with indexes |
| `management/commands/run_workflow_scheduled_triggers.py` | `contract_expiring` trigger |
| `tests/test_models.py` | 14 model tests |
| `tests/test_conditions.py` | 49 condition/operator tests |
| `tests/test_engine.py` | 21 engine tests |
| `tests/test_views.py` | 33 view tests |

### Modifications to Existing Files

| File | Change |
|------|--------|
| `hr_api/settings.py` | Added `apps.workflows` to INSTALLED_APPS |
| `hr_api/urls.py` | Added `path('api/', include('apps.workflows.urls'))` |
| `apps/recruitment/models.py` | Added `recruiter_id` (UUID, nullable) to Candidate |
| `apps/recruitment/migrations/0004_candidate_recruiter_id.py` | Migration for recruiter_id |
| `apps/core/management/commands/seed_rbac.py` | Added 'workflows' module + grants to _HR_GRANTS |
| `apps/core/migrations/0009_workflows_rbac.py` | Grants `workflows.view/manage` to HR roles |
| `apps/actions/generators/workflow.py` | WorkflowTask → ActionItem generator (new file) |
| `apps/actions/apps.py` | Imports workflow generator in ready() |

---

## Architecture Decisions

1. **Signal decoupling**: Signal handler functions live in `signals.py` but are connected in `apps.py.ready()` after all apps are loaded — avoids circular imports entirely.
2. **Executor registry**: Executors registered with `@ExecutorRegistry.register(type)` decorator at class definition time. Registry is populated when `executors.py` is imported (also in ready()).
3. **Idempotency**: Engine queries for existing `status='completed'` execution before creating a new one. No unique constraint used — allows retries on failed/skipped executions.
4. **Context dict**: All trigger contexts use flat string-keyed dicts. `_render()` substitutes `{{key}}` templates in action params.
5. **Numeric operators** (`lt/lte/gt/gte`): Use `float()` conversion — raises ValueError for non-numeric inputs, caught by ConditionEvaluator as False.

---

## API Endpoints

| URL | Methods | Description |
|-----|---------|-------------|
| `/api/workflows/` | GET, POST | List / create workflow definitions |
| `/api/workflows/<uuid>/` | GET, PUT, PATCH, DELETE | Retrieve / update / delete |
| `/api/workflows/<uuid>/activate/` | POST | Enable workflow |
| `/api/workflows/<uuid>/deactivate/` | POST | Disable workflow |
| `/api/workflows/executions/` | GET | List executions (filter: workflow, status) |
| `/api/workflows/executions/<uuid>/` | GET | Retrieve execution with logs |
| `/api/workflows/templates/` | GET | Built-in template library (5 templates) |
| `/api/workflows/tasks/` | GET, POST | List / create tasks |
| `/api/workflows/tasks/<uuid>/` | GET, PUT, PATCH, DELETE | Task CRUD |
| `/api/workflows/tasks/<uuid>/complete/` | POST | Mark task completed |

---

## Test Results

```
Ran 100 tests in 42.6s — OK
  test_conditions: 49 tests
  test_engine: 21 tests
  test_models: 14 tests
  test_views: 33 tests (including 3 template tests, 7 execution tests, 8 task tests, 13 definition tests)

No regressions in apps.actions (52 tests still passing)
```

---

## Known Limitations / Future Work

- `performance_review_due` scheduled trigger not implemented (no PerformanceReview trigger model yet — Phase 7)
- `assign_manager` executor sets `manager_id` on EmployeeProfile but no notification is sent (can be chained with `send_notification` in the same workflow)
- `schedule_interview` uses `scheduled_at_offset_days` param (default 7) since there's no calendar integration
- WorkflowTask visibility in Action Center: `WorkflowTaskGenerator` serves open tasks; the Action Center cache (300s TTL) means new tasks may take up to 5 minutes to appear
