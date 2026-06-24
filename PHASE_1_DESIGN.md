# Phase 1 — Workflow Automation Engine: Design

Generated: 2026-06-24

---

## 1. Objective

Replace hardcoded state transitions with a configurable trigger → condition → action pipeline. HR admins define workflows through the API; the engine fires them at runtime via Django signals.

---

## 2. Models

### WorkflowDefinition
Stores a named automation rule per company.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| company_id | UUID | db_index, tenant scoping |
| tenant_id | UUID nullable | |
| name | CharField(200) | |
| description | TextField | |
| trigger_type | CharField(100) | choices: 10 trigger types |
| condition_logic | CharField(3) | 'AND' or 'OR' |
| conditions | JSONField(list) | list of `{field, operator, value}` dicts |
| actions | JSONField(list) | list of `{type, params}` dicts |
| is_active | BooleanField | default True |

**Index**: `(company_id, trigger_type, is_active)`

### WorkflowExecution
Immutable audit record for each time the engine fires.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| workflow | FK → WorkflowDefinition | CASCADE |
| trigger_type | CharField | snapshot |
| source_object_id | CharField(200) | str(triggering object PK) |
| status | CharField | pending / running / completed / failed / skipped |
| context | JSONField | snapshot of trigger context dict |
| error_message | TextField | |
| started_at, completed_at | DateTimeField nullable | |
| attempt_count | PositiveIntegerField | retry counter |

### WorkflowExecutionLog
One row per action step in an execution.

| Field | Type | Notes |
|-------|------|-------|
| id | BigAutoField PK | |
| execution | FK → WorkflowExecution | CASCADE |
| step | PositiveIntegerField | action index |
| action_type | CharField | |
| status | CharField | success / failed / skipped |
| message | TextField | executor return value or error |
| executed_at | DateTimeField | auto_now_add |

### WorkflowTask
Tasks created by the `create_task` / `create_action_item` executors. Surfaced in Action Center via a generator.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| company_id | UUID | db_index |
| execution | FK → WorkflowExecution nullable | SET_NULL |
| title | CharField(300) | |
| description | TextField | |
| assigned_to | UUID nullable | user/employee |
| due_date | DateTimeField nullable | |
| status | CharField | open / in_progress / completed / cancelled |
| priority | CharField | low / normal / high / urgent |
| completed_at | DateTimeField nullable | |
| source_module | CharField(100) | |
| source_record_id | CharField(200) | |

**Indexes**: `(company_id, status)`, `(assigned_to, status)`

---

## 3. Trigger Types (10)

| Trigger | Signal Source | When |
|---------|--------------|------|
| `candidate_applied` | Candidate post_save created=True | New candidate submits application |
| `candidate_stage_changed` | Candidate post_save created=False | `current_stage` changes |
| `interview_completed` | Interview post_save | `status` changes to 'completed' |
| `employee_created` | EmployeeProfile post_save created=True | New employee profile |
| `leave_submitted` | LeaveRequest post_save created=True | Employee submits leave |
| `leave_approved` | LeaveRequest post_save | `status` changes to 'approved' |
| `leave_rejected` | LeaveRequest post_save | `status` changes to 'rejected' |
| `contract_expiring` | Management command `run_workflow_scheduled_triggers` | N days before end_date |
| `performance_review_due` | Management command | Scheduled trigger |
| `exit_process_started` | EmployeeExit post_save created=True | Exit record created |

---

## 4. Condition Operators (14)

`eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `contains`, `not_contains`, `in`, `not_in`, `is_null`, `is_not_null`, `starts_with`, `ends_with`

Condition structure:
```json
{"field": "candidate_ai_score", "operator": "gte", "value": "80"}
```

Field values are dot-notation paths into the flat context dict. `condition_logic` = 'AND' (all must match) or 'OR' (any must match). Empty conditions list always passes.

---

## 5. Action Types (8)

| Type | Description |
|------|------------|
| `send_notification` | `notify()` via apps.core.services.notifications |
| `send_email` | Direct email with `{{key}}` template rendering |
| `create_task` | Creates a WorkflowTask record |
| `create_action_item` | Creates a WorkflowTask surfaced in Action Center |
| `assign_recruiter` | Sets `recruiter_id` on Candidate |
| `assign_manager` | Sets `manager_id` on EmployeeProfile |
| `schedule_interview` | Creates an Interview record |
| `escalate_approval` | Sends escalation notification via `action.escalated` template |

Action structure:
```json
{"type": "send_email", "params": {"recipient": "{{candidate_email}}", "subject": "..."}}
```

---

## 6. Engine Architecture

```
WorkflowEngine.fire(trigger_type, context, company_id)
    ↓
Query WorkflowDefinition WHERE trigger_type=? AND is_active=True AND company_id=?
    ↓ for each matching workflow
_execute(workflow, context, company_id)
    ↓
Idempotency check: skip if existing completed execution
    ↓
ConditionEvaluator.evaluate(conditions, context, logic)
    ↓ if conditions met
ExecutorRegistry.get(action_type).execute(params, context, execution)  per action
    ↓
WorkflowExecutionLog row per step
    ↓
execution.status = completed/failed/skipped
    ↓
ServiceAuditLog.log('workflow.executed', ...)
```

**Transaction**: actions run inside `transaction.atomic()`. A failed action logs 'failed' but does not rollback other actions.

**Idempotency**: Engine queries for `status='completed'` before creating a new execution. Retry is allowed by deleting or marking the failed execution.

---

## 7. Context Dict Keys

All contexts include `id` (string, source object PK) and `company_id`.

**candidate_applied / candidate_stage_changed**:
`candidate_id`, `candidate_name`, `candidate_email`, `candidate_phone`, `candidate_current_stage`, `candidate_ai_score`, `candidate_source`, `candidate_previous_stage` (stage_changed only), `job_posting_id`, `job_posting_title`, `job_posting_department`

**interview_completed**:
`interview_id`, `interview_type`, `interview_status`, `interview_feedback_score`, `interview_notes`, `candidate_id`, `candidate_name`, `candidate_email`, `job_posting_id`, `job_posting_title`

**leave_submitted / leave_approved / leave_rejected**:
`leave_id`, `leave_type`, `leave_status`, `employee_id`, `start_date`, `end_date`, `days_requested`, `reason`

**employee_created**:
`employee_id`, `employee_number`, `job_title`, `employment_type`, `start_date`

**contract_expiring**:
`employee_id`, `employee_number`, `job_title`, `contract_end_date`, `days_until_expiry`

**exit_process_started**:
`exit_id`, `exit_kind`, `exit_status`, `exit_reason`, `employee_id`, `notice_date`, `last_working_day`

---

## 8. API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET, POST | `/api/workflows/` | List / create definitions |
| GET, PUT, PATCH, DELETE | `/api/workflows/<uuid:pk>/` | Retrieve / update / delete |
| POST | `/api/workflows/<uuid:pk>/activate/` | Toggle is_active=True |
| POST | `/api/workflows/<uuid:pk>/deactivate/` | Toggle is_active=False |
| GET | `/api/workflows/executions/` | List executions (filter: workflow, status) |
| GET | `/api/workflows/executions/<uuid:pk>/` | Retrieve execution + logs |
| GET | `/api/workflows/templates/` | Built-in template library |
| GET, POST | `/api/workflows/tasks/` | List / create tasks |
| GET, PUT, PATCH, DELETE | `/api/workflows/tasks/<uuid:pk>/` | Retrieve / update / delete task |
| POST | `/api/workflows/tasks/<uuid:pk>/complete/` | Mark task completed |

**RBAC module**: `workflows` — granted to `internal_hr`, `deployed_hr`, `company_admin`, `super_admin`

---

## 9. Codebase Additions

- `apps/workflows/` — new app
- `apps/actions/generators/workflow.py` — WorkflowTask → ActionItem generator
- `apps/recruitment/models.py` — add `recruiter_id` (UUID, nullable) to Candidate
- `apps/core/migrations/0009_workflows_rbac.py` — grant workflows.view/manage to HR roles
- `apps/recruitment/migrations/0004_candidate_recruiter_id.py` — add recruiter_id column

---

## 10. Built-in Templates (5)

1. `candidate-welcome-email` — send confirmation email on application
2. `interview-followup-task` — create task when interview is completed
3. `leave-submission-notify` — create task when leave is submitted
4. `exit-process-checklist` — create action item when exit is initiated
5. `high-score-candidate-fast-track` — create urgent task when candidate AI score ≥ 80
