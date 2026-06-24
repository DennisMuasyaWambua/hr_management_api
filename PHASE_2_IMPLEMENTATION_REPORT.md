# Phase 2 — ATS Candidate CRM: Implementation Report

Completed: 2026-06-24

---

## Status: ✅ Complete — 49/49 tests passing

---

## What Was Built

### Candidate Model Extensions (migration 0005)

7 new fields on existing `Candidate` model:

| Field | Type |
|-------|------|
| `is_passive` | BooleanField default False |
| `availability_date` | DateField nullable |
| `location` | CharField(200) nullable |
| `experience_years` | PositiveIntegerField nullable |
| `education_level` | CharField(20) nullable, choices: high_school/bachelors/masters/phd/other |
| `linkedin_url` | CharField(500) nullable |
| `skills` | JSONField(list) |

### New Models (migration 0006)

8 new models in `apps/recruitment/models.py`:

| Model | db_table | Notes |
|-------|----------|-------|
| `TalentPool` | `talent_pools` | TenantStamped, name/description/criteria/is_active/created_by |
| `TalentPoolMember` | `talent_pool_members` | UUID PK, unique(pool, candidate) |
| `CandidateTag` | `candidate_tags` | TenantStamped, unique(company_id, name) |
| `CandidateTagAssignment` | `candidate_tag_assignments` | UUID PK, unique(tag, candidate) |
| `CandidateNote` | `candidate_notes` | TenantStamped, 5 note types, ordering=-created_at |
| `CandidateActivity` | `candidate_activities` | UUID PK, 14 event types, company_id+candidate_id index |
| `Referral` | `referrals` | TenantStamped, 4 statuses, bonus_amount/bonus_paid_at |
| `CandidateScoreBreakdown` | `candidate_score_breakdowns` | OneToOne → Candidate |

### New Files

| File | Purpose |
|------|---------|
| `apps/recruitment/crm_serializers.py` | Serializers for all 8 CRM models |
| `apps/recruitment/crm_views.py` | ViewSets + CandidateSearchView |
| `apps/recruitment/migrations/0005_candidate_crm_fields.py` | Candidate CRM field additions |
| `apps/recruitment/migrations/0006_crm_models.py` | All 8 CRM model tables |
| `apps/recruitment/tests/__init__.py` | Test package |
| `apps/recruitment/tests/test_crm.py` | 49 tests across 7 test classes |
| `apps/core/migrations/0010_crm_rbac.py` | RBAC grants for talent_pools + referrals |

### Modified Files

| File | Change |
|------|--------|
| `apps/recruitment/models.py` | +7 Candidate fields, +8 new CRM model classes |
| `apps/recruitment/urls.py` | +6 router registrations + candidate-search/ path |
| `apps/core/management/commands/seed_rbac.py` | Added talent_pools, referrals to MODULES + _HR_GRANTS |

---

## API Endpoints Added

| URL | Methods | rbac_module |
|-----|---------|-------------|
| `/api/talent-pools/` | GET, POST | talent_pools |
| `/api/talent-pools/<uuid>/` | GET, PUT, PATCH, DELETE | talent_pools |
| `/api/talent-pools/<uuid>/add-candidate/` | POST | talent_pools |
| `/api/talent-pools/<uuid>/remove-candidate/` | POST | talent_pools |
| `/api/talent-pools/<uuid>/members/` | GET | talent_pools |
| `/api/candidate-tags/` | GET, POST | recruitment |
| `/api/candidate-tags/<uuid>/` | GET, PUT, PATCH, DELETE | recruitment |
| `/api/candidate-tag-assignments/` | GET, POST, DELETE | recruitment |
| `/api/candidate-notes/` | GET, POST | recruitment |
| `/api/candidate-notes/<uuid>/` | GET, PUT, PATCH, DELETE | recruitment |
| `/api/candidate-activities/` | GET only | recruitment |
| `/api/referrals/` | GET, POST | referrals |
| `/api/referrals/<uuid>/` | GET, PUT, PATCH, DELETE | referrals |
| `/api/candidate-search/` | GET | recruitment |

---

## Auto-Activity Creation

| Trigger | Event Type |
|---------|-----------|
| CandidateNote created | `note_added` |
| CandidateTagAssignment created | `tag_added` |
| CandidateTagAssignment deleted | `tag_removed` |
| TalentPoolMember created | `pool_added` |
| TalentPoolMember deleted | `pool_removed` |
| Referral created | `referral_submitted` |

---

## Advanced Search (GET /api/candidate-search/)

Supports: `q`, `skills`, `location`, `experience_min`, `experience_max`, `education_level`, `availability_before`, `is_passive`, `stage`, `pool_id`, `tag_ids`, `page`, `page_size` (max 100).

---

## Architecture Decisions

1. **Separate file pair** (`crm_serializers.py` + `crm_views.py`): keeps Phase 2 code isolated from existing `serializers.py` and `views.py`; avoids touching the careers-site-facing public endpoints.
2. **CandidateActivity is write-via-side-effects only**: the ViewSet is read-only (`http_method_names = ['get', 'head', 'options']`). Activities are created by CRM operations, not directly via API. This maintains timeline integrity.
3. **IntegrityError → 409 on duplicate pool membership**: avoids a separate pre-check DB round-trip; DB unique constraint is the authoritative guard.
4. **Migration 0010 re-grants recruitment.view/manage**: migration 0007 ran before roles were seeded by 0008, so the loop found no roles and was a no-op. Migration 0010 fixes this idempotently with get_or_create.

---

## Test Results

```
Ran 49 tests in 69s — OK
  TestTalentPoolViewSet: 15 tests
  TestCandidateTagViewSet: 4 tests
  TestCandidateTagAssignmentViewSet: 4 tests
  TestCandidateNoteViewSet: 5 tests
  TestCandidateActivityViewSet: 3 tests
  TestReferralViewSet: 5 tests
  TestCandidateSearchView: 13 tests

No regressions: apps.workflows 100 tests still passing
```
