"""Unit tests for the rule-based scoring algorithm — no DB required."""
from unittest.mock import MagicMock

from django.test import TestCase

from apps.matching.providers.rule_based import (
    RuleBasedProvider,
    _education_score,
    _experience_score,
    _location_score,
    _skill_score,
)


def _candidate(**kwargs):
    c = MagicMock()
    c.skills = kwargs.get('skills', [])
    c.ai_extracted_skills = kwargs.get('ai_extracted_skills', [])
    c.cv_text = kwargs.get('cv_text', '')
    c.experience_years = kwargs.get('experience_years', None)
    c.ai_experience_years = kwargs.get('ai_experience_years', None)
    c.education_level = kwargs.get('education_level', None)
    c.ai_education = kwargs.get('ai_education', '')
    c.location = kwargs.get('location', '')
    c.company_id = kwargs.get('company_id', None)
    c.ai_score = None
    return c


def _posting(**kwargs):
    p = MagicMock()
    p.required_keywords = kwargs.get('required_keywords', [])
    p.nice_to_have_keywords = kwargs.get('nice_to_have_keywords', [])
    p.experience_level = kwargs.get('experience_level', '')
    p.location_name = kwargs.get('location_name', '')
    return p


class TestSkillScore(TestCase):

    def test_no_required_keywords_returns_75(self):
        c = _candidate()
        p = _posting()
        score, _ = _skill_score(c, p)
        self.assertEqual(score, 75.0)

    def test_all_required_matched_returns_100(self):
        c = _candidate(skills=['Python', 'Django'])
        p = _posting(required_keywords=['python', 'django'])
        score, _ = _skill_score(c, p)
        self.assertEqual(score, 100.0)

    def test_no_required_matched_returns_0(self):
        c = _candidate(skills=['Java'])
        p = _posting(required_keywords=['python', 'django'])
        score, _ = _skill_score(c, p)
        self.assertEqual(score, 0.0)

    def test_partial_match_proportional(self):
        c = _candidate(skills=['python'])
        p = _posting(required_keywords=['python', 'django'])
        score, _ = _skill_score(c, p)
        self.assertAlmostEqual(score, 50.0)

    def test_match_from_ai_extracted_skills(self):
        c = _candidate(ai_extracted_skills=['python'])
        p = _posting(required_keywords=['python'])
        score, _ = _skill_score(c, p)
        self.assertEqual(score, 100.0)

    def test_match_from_cv_text(self):
        c = _candidate(cv_text='Experienced with Python and Django frameworks')
        p = _posting(required_keywords=['python'])
        score, _ = _skill_score(c, p)
        self.assertEqual(score, 100.0)

    def test_nice_to_have_bonus_adds_to_score(self):
        c = _candidate(skills=['python', 'docker'])
        p = _posting(required_keywords=['python'], nice_to_have_keywords=['docker'])
        score, _ = _skill_score(c, p)
        self.assertGreater(score, 100.0 - 1e-9)  # capped at 100

    def test_nice_to_have_does_not_exceed_100(self):
        c = _candidate(skills=['python', 'docker', 'kubernetes'])
        p = _posting(
            required_keywords=['python'],
            nice_to_have_keywords=['docker', 'kubernetes'],
        )
        score, _ = _skill_score(c, p)
        self.assertLessEqual(score, 100.0)

    def test_keywords_case_insensitive(self):
        c = _candidate(skills=['PYTHON'])
        p = _posting(required_keywords=['Python'])
        score, _ = _skill_score(c, p)
        self.assertEqual(score, 100.0)

    def test_notes_list_required_missing(self):
        c = _candidate(skills=['java'])
        p = _posting(required_keywords=['python'])
        _, notes = _skill_score(c, p)
        self.assertTrue(any('missing' in n for n in notes))

    def test_notes_list_required_matched(self):
        c = _candidate(skills=['python'])
        p = _posting(required_keywords=['python'])
        _, notes = _skill_score(c, p)
        self.assertTrue(any('matched' in n for n in notes))


class TestExperienceScore(TestCase):

    def test_no_years_returns_50_neutral(self):
        c = _candidate()
        p = _posting(experience_level='senior')
        score, _ = _experience_score(c, p)
        self.assertEqual(score, 50.0)

    def test_no_experience_level_returns_75_neutral(self):
        c = _candidate(experience_years=5)
        p = _posting(experience_level='')
        score, _ = _experience_score(c, p)
        self.assertEqual(score, 75.0)

    def test_meets_senior_threshold(self):
        c = _candidate(experience_years=6)
        p = _posting(experience_level='senior')
        score, _ = _experience_score(c, p)
        self.assertEqual(score, 100.0)

    def test_below_entry_threshold(self):
        c = _candidate(experience_years=0)
        p = _posting(experience_level='mid')
        score, _ = _experience_score(c, p)
        self.assertEqual(score, 0.0)

    def test_partial_experience_proportional(self):
        c = _candidate(experience_years=1)
        p = _posting(experience_level='mid')
        score, _ = _experience_score(c, p)
        # mid requires 2y minimum; 1/2 = 50%
        self.assertAlmostEqual(score, 50.0)

    def test_falls_back_to_ai_experience_years(self):
        c = _candidate(ai_experience_years=6.0)
        p = _posting(experience_level='senior')
        score, _ = _experience_score(c, p)
        self.assertEqual(score, 100.0)

    def test_explicit_experience_years_preferred_over_ai(self):
        c = _candidate(experience_years=3, ai_experience_years=10.0)
        p = _posting(experience_level='senior')
        score, _ = _experience_score(c, p)
        # 3 < 5 (senior min), so should be partial, not 100
        self.assertLess(score, 100.0)

    def test_lead_level_threshold(self):
        c = _candidate(experience_years=10)
        p = _posting(experience_level='lead')
        score, _ = _experience_score(c, p)
        self.assertEqual(score, 100.0)


class TestEducationScore(TestCase):

    def test_bachelors_returns_70(self):
        c = _candidate(education_level='bachelors')
        score, _ = _education_score(c)
        self.assertEqual(score, 70.0)

    def test_masters_returns_85(self):
        c = _candidate(education_level='masters')
        score, _ = _education_score(c)
        self.assertEqual(score, 85.0)

    def test_phd_returns_100(self):
        c = _candidate(education_level='phd')
        score, _ = _education_score(c)
        self.assertEqual(score, 100.0)

    def test_high_school_returns_20(self):
        c = _candidate(education_level='high_school')
        score, _ = _education_score(c)
        self.assertEqual(score, 20.0)

    def test_no_data_returns_60_neutral(self):
        c = _candidate()
        score, _ = _education_score(c)
        self.assertEqual(score, 60.0)

    def test_ai_education_phd_parsed(self):
        c = _candidate(ai_education='PhD in Computer Science')
        score, _ = _education_score(c)
        self.assertEqual(score, 100.0)

    def test_ai_education_masters_parsed(self):
        c = _candidate(ai_education='MSc Data Science, University of Nairobi')
        score, _ = _education_score(c)
        self.assertEqual(score, 85.0)

    def test_ai_education_bachelors_parsed(self):
        c = _candidate(ai_education='Bachelor of Science in Engineering')
        score, _ = _education_score(c)
        self.assertEqual(score, 70.0)


class TestLocationScore(TestCase):

    def test_matching_city_returns_100(self):
        c = _candidate(location='Nairobi Kenya')
        p = _posting(location_name='Nairobi')
        score, _ = _location_score(c, p)
        self.assertEqual(score, 100.0)

    def test_no_match_returns_0(self):
        c = _candidate(location='Mombasa')
        p = _posting(location_name='Nairobi')
        score, _ = _location_score(c, p)
        self.assertEqual(score, 0.0)

    def test_blank_candidate_location_returns_50_neutral(self):
        c = _candidate(location='')
        p = _posting(location_name='Nairobi')
        score, _ = _location_score(c, p)
        self.assertEqual(score, 50.0)

    def test_blank_job_location_returns_50_neutral(self):
        c = _candidate(location='Nairobi')
        p = _posting(location_name='')
        score, _ = _location_score(c, p)
        self.assertEqual(score, 50.0)

    def test_case_insensitive_match(self):
        c = _candidate(location='NAIROBI')
        p = _posting(location_name='nairobi')
        score, _ = _location_score(c, p)
        self.assertEqual(score, 100.0)


class TestRuleBasedProviderTotal(TestCase):

    def test_total_is_weighted_sum(self):
        provider = RuleBasedProvider()
        c = _candidate(
            skills=['python'],
            experience_years=6,
            education_level='masters',
            location='Nairobi',
        )
        p = _posting(
            required_keywords=['python'],
            experience_level='senior',
            location_name='Nairobi',
        )
        result = provider.score(c, p)
        expected = round(
            0.4 * 100.0 + 0.3 * 100.0 + 0.2 * 85.0 + 0.1 * 100.0, 2)
        self.assertAlmostEqual(result.total_score, expected, places=1)

    def test_result_is_named_tuple(self):
        provider = RuleBasedProvider()
        c = _candidate()
        p = _posting()
        result = provider.score(c, p)
        self.assertIsNotNone(result.skill_score)
        self.assertIsNotNone(result.total_score)
        self.assertIsInstance(result.notes, str)

    def test_score_is_between_0_and_100(self):
        provider = RuleBasedProvider()
        for _ in range(5):
            c = _candidate(
                skills=['python', 'java'],
                experience_years=3,
                education_level='bachelors',
                location='Kisumu',
            )
            p = _posting(
                required_keywords=['python', 'go'],
                nice_to_have_keywords=['docker'],
                experience_level='senior',
                location_name='Nairobi',
            )
            result = provider.score(c, p)
            self.assertGreaterEqual(result.total_score, 0.0)
            self.assertLessEqual(result.total_score, 100.0)

    def test_provider_name(self):
        provider = RuleBasedProvider()
        self.assertEqual(provider.name, 'rule_based')
