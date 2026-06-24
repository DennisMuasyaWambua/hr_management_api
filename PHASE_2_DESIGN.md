# Phase 2 — ATS Candidate CRM: Design

Generated: 2026-06-24

---

## 1. Objective

Add a structured CRM layer on top of the existing Candidate model: talent pools, tags, activity timelines, notes, referrals, and advanced search. All additions live in `apps/recruitment/`.

---

## 2. Candidate Model Extensions

Fields added to the existing `Candidate` model (migration 0005):

| Field | Type | Notes |
|-------|------|-------|
| `is_passive` | BooleanField | default False — not actively applying |
| `availability_date` | DateField nullable | when passive candidate is available |
| `location` | CharField(200) nullable | candidate's location |
| `experience_years` | PositiveIntegerField nullable | explicit override of ai_experience_years |
| `education_level` | CharField(20) nullable | choices: high_school, bachelors, masters, phd, other |
| `linkedin_url` | CharField(500) nullable | |
| `skills` | JSONField(list) | list of skill strings |

---

## 3. New Models (migration 0006)

### TalentPool
Company-scoped named collection of candidates.

| Field | Type |
|-------|------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped |
| name | CharField(200) |
| description | TextField |
| criteria | JSONField — stored search criteria for re-running |
| is_active | BooleanField default True |
| created_by | UUIDField nullable |

**db_table**: `talent_pools`

### TalentPoolMember
Through model linking Candidate → TalentPool.

| Field | Type |
|-------|------|
| id | UUID PK |
| created_at | auto_now_add |
| pool | FK TalentPool CASCADE |
| candidate | FK Candidate CASCADE |
| added_by | UUIDField nullable |
| notes | TextField |

**Unique**: `(pool, candidate)`  
**db_table**: `talent_pool_members`

### CandidateTag
Tag definitions per company.

| Field | Type |
|-------|------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped |
| name | CharField(100) |
| color | CharField(20) default '#6B7280' |

**Unique**: `(company_id, name)`  
**db_table**: `candidate_tags`

### CandidateTagAssignment
M2M link: Candidate ↔ CandidateTag.

| Field | Type |
|-------|------|
| id | UUID PK |
| created_at | auto_now_add |
| tag | FK CandidateTag CASCADE |
| candidate | FK Candidate CASCADE |

**Unique**: `(tag, candidate)`  
**db_table**: `candidate_tag_assignments`

### CandidateNote
Notes on a candidate (calls, emails, meetings).

| Field | Type |
|-------|------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped |
| candidate | FK Candidate CASCADE |
| note_type | CharField choices: call, email, meeting, note, linkedin |
| body | TextField |
| author_id | UUIDField nullable |
| author_name | CharField(200) snapshot |

**db_table**: `candidate_notes`  
**ordering**: `['-created_at']`

### CandidateActivity
Immutable timeline of activity on a candidate.

| Field | Type |
|-------|------|
| id | UUID PK |
| created_at | auto_now_add |
| company_id | UUID db_index |
| candidate | FK Candidate CASCADE |
| event_type | CharField(50) choices: 14 event types |
| description | TextField |
| actor_id | UUIDField nullable |
| actor_name | CharField(200) snapshot |
| metadata | JSONField |

**db_table**: `candidate_activities`  
**ordering**: `['-created_at']`  
**Index**: `(company_id, candidate_id)`

### Referral
Tracks who referred a candidate.

| Field | Type |
|-------|------|
| id, created_at, updated_at, company_id, tenant_id | TenantStamped |
| candidate | FK Candidate CASCADE |
| referrer_employee_id | UUIDField nullable |
| referrer_name | CharField(200) |
| referrer_email | EmailField |
| status | CharField choices: pending, hired, rejected, withdrawn |
| notes | TextField |
| bonus_amount | DecimalField nullable |
| bonus_paid_at | DateTimeField nullable |

**db_table**: `referrals`

### CandidateScoreBreakdown
Structured score breakdown (populated by Phase 4 AI Matching).

| Field | Type |
|-------|------|
| id | UUID PK |
| created_at, updated_at | auto |
| company_id | UUID db_index |
| candidate | OneToOneField Candidate CASCADE |
| skill_score | FloatField nullable |
| experience_score | FloatField nullable |
| industry_score | FloatField nullable |
| location_score | FloatField nullable |
| total_score | FloatField nullable |
| scoring_notes | TextField |
| scored_at | DateTimeField nullable |

**db_table**: `candidate_score_breakdowns`

---

## 4. API Endpoints

All under `/api/` prefix.

| URL | Method | View | RBAC |
|-----|--------|------|------|
| `talent-pools/` | GET, POST | TalentPoolViewSet.list/create | talent_pools.view/manage |
| `talent-pools/<uuid>/` | GET, PUT, PATCH, DELETE | TalentPoolViewSet.detail | talent_pools |
| `talent-pools/<uuid>/add-candidate/` | POST | TalentPoolViewSet@add_candidate | talent_pools.manage |
| `talent-pools/<uuid>/remove-candidate/` | POST | TalentPoolViewSet@remove_candidate | talent_pools.manage |
| `talent-pools/<uuid>/members/` | GET | TalentPoolViewSet@members | talent_pools.view |
| `candidate-tags/` | GET, POST | CandidateTagViewSet | recruitment |
| `candidate-tags/<uuid>/` | GET, PUT, PATCH, DELETE | CandidateTagViewSet | recruitment |
| `candidate-tag-assignments/` | GET, POST, DELETE | CandidateTagAssignmentViewSet | recruitment |
| `candidate-notes/` | GET, POST | CandidateNoteViewSet (filter by candidate_id) | recruitment |
| `candidate-notes/<uuid>/` | GET, PUT, PATCH, DELETE | CandidateNoteViewSet | recruitment |
| `candidate-activities/` | GET | CandidateActivityViewSet (filter by candidate_id) | recruitment |
| `referrals/` | GET, POST | ReferralViewSet | referrals |
| `referrals/<uuid>/` | GET, PUT, PATCH, DELETE | ReferralViewSet | referrals |
| `candidate-search/` | GET | CandidateSearchView | recruitment |

---

## 5. Advanced Search Parameters (GET /api/candidate-search/)

| Param | Description |
|-------|-------------|
| `q` | Text search across name, email, skills |
| `skills` | Comma-separated skill names (any match) |
| `location` | Substring match on location |
| `experience_min` / `experience_max` | Experience years range |
| `education_level` | Exact match |
| `availability_before` | Date filter on availability_date |
| `is_passive` | true/false |
| `stage` | current_stage filter |
| `pool_id` | Only candidates in this talent pool |
| `tag_ids` | Comma-separated tag UUIDs (any match) |

---

## 6. RBAC Modules Added

| Module | Grants to |
|--------|----------|
| `talent_pools` | internal_hr, deployed_hr |
| `referrals` | internal_hr, deployed_hr |

---

## 7. Auto-Activity Creation

- When a `CandidateNote` is created → activity `note_added`
- When a `CandidateTagAssignment` is created → activity `tag_added`
- When a `CandidateTagAssignment` is deleted → activity `tag_removed`
- When a `TalentPoolMember` is created → activity `pool_added`
- When a `TalentPoolMember` is deleted → activity `pool_removed`
