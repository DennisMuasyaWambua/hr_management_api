# Phase 4 — AI Matching Engine: Design

Generated: 2026-06-24

---

## 1. Objective

Deterministic scoring engine that ranks candidates against job postings using a
weighted rule-based algorithm. Uses an adapter/provider pattern so a future LLM
or vector-similarity provider can be swapped in by registering a new class.
No external API calls; all scoring is computed locally.

---

## 2. New App: `apps/matching/`

Registered as `apps.matching`, label `matching`.

---

## 3. Architecture

```
MatchingEngine.score(candidate, job_posting)
    └─► ProviderRegistry.get_active()  →  RuleBasedProvider (default)
            └─► score()  →  MatchResult(skill, experience, education, location, total, notes)
                └─► persisted to JobMatchScore
                └─► CandidateScoreBreakdown upserted (overall profile snapshot)
```

### Provider pattern

```python
class BaseMatchingProvider(ABC):
    name: str          # e.g. 'rule_based'
    @abstractmethod
    def score(self, candidate, job_posting) -> MatchResult: ...

class MatchResult(NamedTuple):
    skill_score: float
    experience_score: float
    education_score: float
    location_score: float
    total_score: float
    notes: str

class ProviderRegistry:
    _providers: dict[str, BaseMatchingProvider] = {}
    @classmethod def register(cls, provider): ...
    @classmethod def get(cls, name) -> BaseMatchingProvider: ...
    @classmethod def get_active(cls) -> BaseMatchingProvider: ...  # reads MATCHING_PROVIDER setting
```

### RuleBasedProvider scoring

Weights: skill=40%, experience=30%, education=20%, location=10%

**Skill score (0–100)**
- Collect candidate skill corpus: `skills` (Phase 2 JSONField) + `ai_extracted_skills` + `cv_text` (lowercased)
- For each required_keyword in JobPosting: +100/len(required_keywords) if found in corpus
- Bonus up to +20 for nice_to_have_keywords hits; total capped at 100

**Experience score (0–100)**
- Map JobPosting.experience_level → expected years range:
  `entry`: 0–2, `junior`: 0–3, `mid`: 2–5, `senior`: 5–10, `lead`/`principal`: 8+
- Candidate years: `experience_years` (Phase 2) if set, else `ai_experience_years`, else None
- If within range or above → 100; if below → proportional partial credit; if None → 50 (neutral)

**Education score (0–100)**
- Education ladder: high_school=20, other=40, bachelors=70, masters=85, phd=100
- Candidate: `education_level` (Phase 2) if set, else parse `ai_education` heuristically
- If job has no education requirement stated: default 75 (neutral pass)

**Location score (0–100)**
- 100 if candidate.location and posting.location_name share a common word (case-insensitive)
- 50 if either is blank (can't compare, neutral)
- 0 if both present but no overlap

**Total** = 0.4×skill + 0.3×experience + 0.2×education + 0.1×location

---

## 4. New Model: `JobMatchScore`

Stored in `apps/matching/`. Per-candidate-per-posting score.

| Field | Type |
|-------|------|
| id | UUID PK |
| created_at | auto_now_add |
| updated_at | auto_now |
| company_id | UUID db_index |
| candidate | FK recruitment.Candidate CASCADE |
| job_posting | FK recruitment.JobPosting CASCADE |
| provider | CharField(50) — which provider produced this score |
| skill_score | FloatField nullable |
| experience_score | FloatField nullable |
| education_score | FloatField nullable |
| location_score | FloatField nullable |
| total_score | FloatField nullable |
| scoring_notes | TextField |
| scored_at | DateTimeField auto_now |

**Unique**: `(candidate, job_posting)` — one score row per pair, upserted on re-score.  
**db_table**: `job_match_scores`  
**Index**: `(company_id, job_posting_id, total_score)`

---

## 5. API Endpoints

| URL | Method | Description | RBAC |
|-----|--------|-------------|------|
| `matching/score/` | POST | Score one candidate vs one job | matching.manage |
| `matching/score-bulk/` | POST | Score all candidates for a job | matching.manage |
| `matching/rank/<uuid:job_posting_id>/` | GET | Ranked candidates for a job | matching.view |
| `matching/results/` | GET | Filter scores: ?candidate_id=, ?job_posting_id= | matching.view |
| `matching/providers/` | GET | List registered providers | matching.view |

### POST /api/matching/score/
Payload: `{ "candidate_id": "<uuid>", "job_posting_id": "<uuid>" }`  
Returns: JobMatchScore JSON.

### POST /api/matching/score-bulk/
Payload: `{ "job_posting_id": "<uuid>", "candidate_ids": ["<uuid>", ...] }`  
If `candidate_ids` omitted → scores ALL candidates for that posting.  
Returns: `{ "scored": N, "results": [...] }`

### GET /api/matching/rank/<job_posting_id>/
Returns candidates ordered by `total_score` desc with their scores.

---

## 6. Settings

`MATCHING_PROVIDER = 'rule_based'` (default). Override in settings to switch providers.

---

## 7. RBAC

Module `matching` → `internal_hr`, `deployed_hr`, `company_admin`, `super_admin`.
