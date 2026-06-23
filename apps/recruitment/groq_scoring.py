"""
Server-side GROQ AI candidate scoring.

Called after a Candidate row is saved in PublicApplyView. Returns a dict
with ai_score, ai_summary, ai_experience_years, ai_education or raises
GroqScoringError so the caller can decide whether to 500 or silently skip.
"""
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'

_SYSTEM_PROMPT = (
    "You are a recruitment AI. Given a job description and a candidate's CV text, "
    "return ONLY a JSON object with these exact keys:\n"
    "  ai_score (float 0-100),\n"
    "  ai_summary (string, 2-3 sentences),\n"
    "  ai_experience_years (float),\n"
    "  ai_education (string, highest qualification).\n"
    "No extra text. No markdown. Pure JSON."
)


class GroqScoringError(Exception):
    pass


def score_candidate(job_title: str, job_description: str, cv_text: str) -> dict:
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        raise GroqScoringError('GROQ_API_KEY not configured')

    user_content = (
        f"Job: {job_title}\n\nDescription:\n{job_description[:2000]}\n\n"
        f"Candidate CV:\n{cv_text[:3000]}"
    )

    try:
        resp = requests.post(
            GROQ_URL,
            headers={'Authorization': f'Bearer {api_key}',
                     'Content-Type': 'application/json'},
            json={
                'model': getattr(settings, 'GROQ_MODEL', 'llama3-70b-8192'),
                'messages': [
                    {'role': 'system', 'content': _SYSTEM_PROMPT},
                    {'role': 'user', 'content': user_content},
                ],
                'temperature': 0.1,
                'max_tokens': 300,
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        raise GroqScoringError(f'GROQ request failed: {exc}') from exc

    if not resp.ok:
        raise GroqScoringError(f'GROQ returned {resp.status_code}: {resp.text[:200]}')

    try:
        content = resp.json()['choices'][0]['message']['content'].strip()
        result = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise GroqScoringError(f'Could not parse GROQ response: {exc}') from exc

    return {
        'ai_score': float(result.get('ai_score', 0)),
        'ai_summary': str(result.get('ai_summary', '')),
        'ai_experience_years': float(result.get('ai_experience_years', 0)),
        'ai_education': str(result.get('ai_education', '')),
    }
