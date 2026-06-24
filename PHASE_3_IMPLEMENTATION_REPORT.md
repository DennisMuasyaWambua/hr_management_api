# Phase 3 — Recruitment Client CRM: Implementation Report

Completed: 2026-06-24

---

## Status: ✅ Complete — 40/40 tests passing

---

## What Was Built

### New App: `apps/crm/`

| File | Purpose |
|------|---------|
| `apps.py` | CrmConfig, label='crm' |
| `models.py` | 6 models |
| `serializers.py` | 6 serializers |
| `views.py` | 6 ViewSets |
| `urls.py` | DefaultRouter registrations |
| `migrations/0001_initial.py` | All 6 tables |
| `tests/test_crm.py` | 40 tests across 6 test classes |

### Models

| Model | db_table | Key Fields |
|-------|----------|-----------|
| `RecruitmentClient` | `crm_clients` | name, industry, status, account_manager_id, is_deleted (soft-delete) |
| `ClientContact` | `crm_client_contacts` | full_name, is_primary, is_hiring_manager |
| `ClientContract` | `crm_contracts` | contract_type, start_date, fee_percentage, replacement_days |
| `ClientSLA` | `crm_slas` | metric, target_days; nested in ClientContract serializer |
| `ClientMeetingNote` | `crm_meeting_notes` | meeting_type, attendees (JSON), action_items (JSON) |
| `Placement` | `crm_placements` | FK→Candidate, FK→RecruitmentClient, FK→ClientContract (nullable) |

### Modifications to Existing Files

| File | Change |
|------|--------|
| `hr_api/settings.py` | Added `apps.crm` to INSTALLED_APPS |
| `hr_api/urls.py` | Added `path('api/', include('apps.crm.urls'))` |
| `apps/core/migrations/0011_crm_rbac.py` | Grants `crm.view/manage` to HR roles |
| `apps/core/management/commands/seed_rbac.py` | Added `crm` to MODULES + `crm.view/manage` to _HR_GRANTS |

---

## API Endpoints

| URL | Methods | Description |
|-----|---------|-------------|
| `/api/clients/` | GET, POST | List/create clients (soft-delete on DELETE) |
| `/api/clients/<uuid>/` | GET, PUT, PATCH, DELETE | Detail (DELETE → soft delete) |
| `/api/clients/<uuid>/contacts/` | GET | Nested contact list |
| `/api/clients/<uuid>/contracts/` | GET | Nested contract list |
| `/api/clients/<uuid>/placements/` | GET | Nested placement list |
| `/api/clients/<uuid>/meeting-notes/` | GET | Nested meeting note list |
| `/api/client-contacts/` | GET, POST | Filter: `?client_id=`, `?is_hiring_manager=` |
| `/api/client-contacts/<uuid>/` | GET, PUT, PATCH, DELETE | |
| `/api/client-contracts/` | GET, POST | Filter: `?client_id=`, `?status=` |
| `/api/client-contracts/<uuid>/` | GET, PUT, PATCH, DELETE | Includes nested `slas` array |
| `/api/client-contracts/<uuid>/slas/` | GET | SLA list for contract |
| `/api/client-slas/` | GET, POST | Filter: `?contract_id=` |
| `/api/client-slas/<uuid>/` | GET, PUT, PATCH, DELETE | |
| `/api/client-meeting-notes/` | GET, POST | Filter: `?client_id=` |
| `/api/client-meeting-notes/<uuid>/` | GET, PUT, PATCH, DELETE | |
| `/api/placements/` | GET, POST | Filter: `?client_id=`, `?status=`, `?candidate_id=` |
| `/api/placements/<uuid>/` | GET, PUT, PATCH, DELETE | |

---

## Architecture Decisions

1. **Soft-delete on RecruitmentClient**: `perform_destroy` sets `is_deleted=True` rather than deleting the row. Client audit history (meetings, placements) is preserved. The queryset base is `filter(is_deleted=False)`.
2. **SLAs nested in ClientContract serializer**: A read-only `slas = ClientSLASerializer(many=True, read_only=True)` field allows the contract detail view to return SLAs inline — matching typical frontend consumption patterns. Mutation of SLAs uses the standalone `/api/client-slas/` endpoint.
3. **author_id stamped via X-User-Id header**: `ClientMeetingNoteViewSet.perform_create` calls `request_user_id(request)` to stamp the author, consistent with CandidateNote pattern from Phase 2.
4. **FK to recruitment models using string label**: `Placement.candidate` uses `'recruitment.Candidate'` string FK to avoid circular import.

---

## Test Results

```
Ran 40 tests in 69s — OK
  TestRecruitmentClientViewSet: 13 tests (incl. soft-delete, search, nested actions)
  TestClientContactViewSet: 6 tests
  TestClientContractViewSet: 6 tests (incl. nested SLA serializer)
  TestClientSLAViewSet: 3 tests
  TestClientMeetingNoteViewSet: 5 tests (incl. author_id stamping)
  TestPlacementViewSet: 7 tests

No regressions: Phase 1 (100) + Phase 2 (49) = 149 tests all still passing
```
