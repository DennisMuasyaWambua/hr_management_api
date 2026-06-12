"""
Smile ID facial-recognition check-in.

Uses Smile ID's Biometric KYC / SmartSelfie Authentication: the PWA captures a
selfie, we verify it against the employee's enrolled reference. Demo mode
(SMILEID_DEMO_MODE, default true) accepts any selfie with confidence 0.99 so
the flow is demonstrable before Smile ID credentials exist.

Env: SMILEID_PARTNER_ID, SMILEID_API_KEY, SMILEID_BASE_URL
     (https://testapi.smileidentity.com / https://api.smileidentity.com)
"""
import base64
import hashlib
import hmac
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SmileIDError(Exception):
    pass


def _demo():
    return getattr(settings, 'SMILEID_DEMO_MODE', True)


def _signature(timestamp: str) -> str:
    key = getattr(settings, 'SMILEID_API_KEY', '')
    partner = getattr(settings, 'SMILEID_PARTNER_ID', '')
    msg = (timestamp + partner + 'sid_request').encode()
    return base64.b64encode(
        hmac.new(key.encode(), msg, hashlib.sha256).digest()).decode()


def verify_selfie(employee_user_id: str, selfie_b64: str) -> dict:
    """
    Returns {'verified': bool, 'confidence': float, 'job_id': str}.
    SmartSelfie Authentication (job_type 2) against the enrolled user.
    """
    if _demo():
        return {'verified': True, 'confidence': 0.99, 'job_id': 'demo',
                'demo': True}

    timestamp = str(int(time.time() * 1000))
    base = getattr(settings, 'SMILEID_BASE_URL',
                   'https://testapi.smileidentity.com/v1')
    payload = {
        'partner_id': getattr(settings, 'SMILEID_PARTNER_ID', ''),
        'signature': _signature(timestamp),
        'timestamp': timestamp,
        'partner_params': {
            'user_id': employee_user_id,
            'job_id': f'checkin-{timestamp}',
            'job_type': 2,  # SmartSelfie Authentication
        },
        'images': [{'image_type_id': 2, 'image': selfie_b64}],
        'source_sdk': 'rest_api',
    }
    resp = requests.post(f'{base}/upload', json=payload, timeout=60)
    if not resp.ok:
        raise SmileIDError(f'Smile ID error {resp.status_code}: {resp.text[:300]}')
    data = resp.json()
    result = data.get('result', data)
    confidence = float(result.get('ConfidenceValue', 0) or 0) / 100.0
    verified = str(result.get('ResultCode', '')) in ('0810', '1210') or confidence >= 0.8
    return {'verified': verified, 'confidence': confidence,
            'job_id': data.get('job_id', '')}
