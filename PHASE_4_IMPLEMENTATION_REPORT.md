# Phase 4 — AI Matching Engine: Implementation Report

Completed: 2026-06-24

---

## Status: ✅ Complete — 57/57 tests passing

---

## What Was Built

### New App: `apps/matching/`

| File | Purpose |
|------|---------|
| `apps.py` | MatchingConfig — imports rule_based provider in ready() |
| `models.py` | JobMatchScore model |
| `engine.py` | MatchingEngine.score/score_bulk/rank |
| `providers/base.py` | BaseMatchingProvider ABC, MatchResult NamedTuple, ProviderRegistry |
| `providers/rule_based.py` | RuleBasedProvider — 4-dimension deterministic scoring |
| `serializers.py` | JobMatchScoreSerializer, RankedCandidateSerializer |
| `views.py` | ScoreView, ScoreBulkView, RankView, ResultsView, ProvidersView |
| `urls.py` | 5 URL patterns |
| `migrations/0001_initial.py` | job_match_scores table |
| `tests/test_scoring.py` | 31 unit tests (pure scoring logic, no DB) |
| `tests/test_views.py` | 26 API integration tests |

### New Model: `JobMatchScore`

| Field | Notes |
|-------|-------|
| candidate + job_posting | FK pair, unique_together → upserted on re-score |
| provider | CharField — which provider produced the score |
| skill_score, experience_score, education_score, location_score | 0–100 per dimension |
| total_score | Weighted sum: skill×40% + experience×30% + education×20% + location×10% |
| scoring_notes | Human-readable explanation of each dimension |

**db_table**: `job_match_scores`

---

## Scoring Algorithm (RuleBasedProvider)

### Skill Score (weight 40%)
- Corpus: `candidate.skills` + `candidate.ai_extracted_skills` + `candidate.cv_text` (all lowercased)
- Required keywords: each match = 100/N points; missing = 0
- Nice-to-have bonus: up to +20, capped at 100
- No keywords on posting → 75 (neutral)

### Experience Score (weight 30%)
- Maps `JobPosting.experience_level` → year ranges: entry(0–2), junior(0–3), mid(2–5), senior(5–10), lead(8+)
- Uses `candidate.experience_years` (Phase 2) first, falls back to `candidate.ai_experience_years`
- Within/above range → 100; below → proportional; no data → 50 (neutral); no requirement → 75

### Education Score (weight 20%)
- Ladder: high_school=20, other=40, bachelors=70, masters=85, phd=100
- Uses `candidate.education_level` (Phase 2) first, then parses `candidate.ai_education` heuristically (checks for "phd", "master", "msc", "bachelor", "bsc")
- No data → 60 (neutral)

### Location Score (weight 10%)
- Tokenizes both strings, checks for any shared word (case-insensitive)
- Match → 100; no match → 0; either blank → 50 (neutral)

---

## Side Effects on Score

Every `MatchingEngine.score()` call:
1. Upserts `JobMatchScore` (update_or_create on candidate+job_posting)
2. Upserts `CandidateScoreBreakdown` (Phase 2 model — overall profile snapshot)
3. Writes `candidate.ai_score = total_score` (existing field on Candidate)

---

## API Endpoints

| URL | Method | Description |
|-----|--------|-------------|
| `/api/matching/score/` | POST | Score one candidate vs one job |
| `/api/matching/score-bulk/` | POST | Score all/selected candidates for a job |
| `/api/matching/rank/<uuid>/` | GET | Ranked candidates for a job, desc by total_score |
| `/api/matching/results/` | GET | Filter by candidate_id / job_posting_id |
| `/api/matching/providers/` | GET | List registered providers + active |

---

## Provider Pattern

```python
# Register a new provider:
class MyLLMProvider(BaseMatchingProvider):
    name = 'my_llm'
    def score(self, candidate, job_posting) -> MatchResult: ...

ProviderRegistry.register(MyLLMProvider())

# Activate via settings:
MATCHING_PROVIDER = 'my_llm'
```

---

## Modifications to Existing Files

| File | Change |
|------|--------|
| `hr_api/settings.py` | Added `apps.matching` |
| `hr_api/urls.py` | Added `path('api/', include('apps.matching.urls'))` |
| `apps/core/migrations/0012_matching_rbac.py` | Grants `matching.view/manage` to HR roles |
| `apps/core/management/commands/seed_rbac.py` | Added `matching` module + grants |

---

## Test Results

```
Ran 57 tests in 45.7s — OK
  test_scoring: 31 unit tests (mock-based, no DB)
    TestSkillScore: 11, TestExperienceScore: 8, TestEducationScore: 8,
    TestLocationScore: 5, TestRuleBasedProviderTotal: 4
  test_views: 26 integration tests
    TestScoreView: 8, TestScoreBulkView: 4, TestRankView: 3,
    TestResultsView: 4, TestProvidersView: 2, (+ regression context)

Total across all phases: 206 tests passing (100+49+40+57)
```
