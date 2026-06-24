from .base import BaseMatchingProvider, MatchResult, ProviderRegistry

_EXPERIENCE_RANGES = {
    'entry': (0, 2),
    'junior': (0, 3),
    'mid': (2, 5),
    'intermediate': (2, 5),
    'senior': (5, 10),
    'lead': (8, 99),
    'principal': (8, 99),
    'manager': (5, 99),
    'director': (8, 99),
}

_EDUCATION_SCORES = {
    'high_school': 20,
    'other': 40,
    'bachelors': 70,
    'masters': 85,
    'phd': 100,
}


def _skill_score(candidate, job_posting) -> tuple[float, list[str]]:
    required = [k.lower() for k in (job_posting.required_keywords or [])]
    nice = [k.lower() for k in (job_posting.nice_to_have_keywords or [])]

    corpus_parts = []
    for s in (candidate.skills or []):
        corpus_parts.append(str(s).lower())
    for s in (candidate.ai_extracted_skills or []):
        corpus_parts.append(str(s).lower())
    if candidate.cv_text:
        corpus_parts.append(candidate.cv_text.lower())
    corpus = ' '.join(corpus_parts)

    hits = []
    misses = []
    if required:
        per_kw = 100.0 / len(required)
        base = 0.0
        for kw in required:
            if kw in corpus:
                base += per_kw
                hits.append(kw)
            else:
                misses.append(kw)
    else:
        base = 75.0

    # Nice-to-have bonus (up to 20 extra points, capped at 100)
    bonus = 0.0
    if nice:
        nice_hits = sum(1 for kw in nice if kw in corpus)
        bonus = min(20.0, (nice_hits / len(nice)) * 20.0)

    score = min(100.0, base + bonus)
    notes_parts = []
    if hits:
        notes_parts.append(f'required matched: {", ".join(hits)}')
    if misses:
        notes_parts.append(f'required missing: {", ".join(misses)}')
    return score, notes_parts


def _experience_score(candidate, job_posting) -> tuple[float, str]:
    level = (job_posting.experience_level or '').lower().strip()
    years_range = _EXPERIENCE_RANGES.get(level)

    cand_years = candidate.experience_years
    if cand_years is None and candidate.ai_experience_years is not None:
        cand_years = candidate.ai_experience_years

    if cand_years is None:
        return 50.0, 'no experience data'

    if years_range is None:
        return 75.0, 'no experience requirement stated'

    lo, hi = years_range
    if cand_years >= lo:
        return 100.0, f'{cand_years}y meets {level} ({lo}–{hi}y)'
    # Partial credit proportional to how close
    ratio = cand_years / lo if lo > 0 else 0.0
    score = round(ratio * 100.0, 1)
    return score, f'{cand_years}y below {level} minimum {lo}y'


def _education_score(candidate) -> tuple[float, str]:
    level = candidate.education_level
    if not level:
        # Try to parse ai_education heuristically
        ai_edu = (candidate.ai_education or '').lower()
        if 'phd' in ai_edu or 'doctorate' in ai_edu:
            level = 'phd'
        elif 'master' in ai_edu or 'msc' in ai_edu or 'mba' in ai_edu:
            level = 'masters'
        elif 'bachelor' in ai_edu or 'bsc' in ai_edu or 'ba ' in ai_edu or 'b.s' in ai_edu:
            level = 'bachelors'
        elif 'diploma' in ai_edu or 'certificate' in ai_edu:
            level = 'other'
        elif 'high school' in ai_edu or 'secondary' in ai_edu:
            level = 'high_school'

    if not level:
        return 60.0, 'no education data'

    score = float(_EDUCATION_SCORES.get(level, 60))
    return score, f'education: {level}'


def _location_score(candidate, job_posting) -> tuple[float, str]:
    cand_loc = (candidate.location or '').lower().strip()
    job_loc = (job_posting.location_name or '').lower().strip()

    if not cand_loc or not job_loc:
        return 50.0, 'location unknown'

    cand_words = set(cand_loc.split())
    job_words = set(job_loc.split())
    if cand_words & job_words:
        return 100.0, f'location match: {cand_loc}'
    return 0.0, f'location mismatch: {cand_loc!r} vs {job_loc!r}'


class RuleBasedProvider(BaseMatchingProvider):
    name = 'rule_based'

    def score(self, candidate, job_posting) -> MatchResult:
        skill, skill_notes = _skill_score(candidate, job_posting)
        experience, exp_note = _experience_score(candidate, job_posting)
        education, edu_note = _education_score(candidate)
        location, loc_note = _location_score(candidate, job_posting)

        total = round(
            0.4 * skill +
            0.3 * experience +
            0.2 * education +
            0.1 * location,
            2,
        )

        all_notes = skill_notes + [exp_note, edu_note, loc_note]
        notes = '; '.join(n for n in all_notes if n)

        return MatchResult(
            skill_score=round(skill, 2),
            experience_score=round(experience, 2),
            education_score=round(education, 2),
            location_score=round(location, 2),
            total_score=total,
            notes=notes,
        )


ProviderRegistry.register(RuleBasedProvider())
