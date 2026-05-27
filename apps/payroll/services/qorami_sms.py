"""
Qorami SMS API Integration Service.

Sends SMS notifications for payroll disbursements.

To set up:
1. Register at https://sms.qorami.io/
2. Get your API key from the dashboard
3. Add credits to your account

Environment variables required:
- QORAMI_API_KEY: Your Qorami API key
- QORAMI_SENDER_ID: Sender ID (default: HRSYSTEM)
"""

import requests
import logging
from typing import Dict, List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class QoramiSMSService:
    """
    Qorami SMS service for sending payment notifications.

    API Docs: https://www.qorami.co.ke/developer
    """

    BASE_URL = 'https://sms.qorami.io/api'

    def __init__(
        self,
        api_key: str = None,
        sender_id: str = None
    ):
        """Initialize Qorami SMS service with credentials."""
        self.api_key = api_key or getattr(settings, 'QORAMI_API_KEY', '')
        self.sender_id = sender_id or getattr(settings, 'QORAMI_SENDER_ID', 'HRSYSTEM')

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authorization."""
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def send_sms(
        self,
        phone: str,
        message: str
    ) -> Dict:
        """
        Send a single SMS message.

        Args:
            phone: Recipient phone number (format: 254XXXXXXXXX or 07XXXXXXXX)
            message: SMS content

        Returns:
            Dict with success status and message details
        """
        try:
            phone = self._normalize_phone(phone)

            if not phone:
                return {'success': False, 'error': 'Invalid phone number'}

            if not self.api_key:
                return {'success': False, 'error': 'Qorami API key not configured'}

            url = f"{self.BASE_URL}/sms/sendmultiple"

            payload = {
                "api_key": self.api_key,
                "mobile": phone,
                "message": message,
                "shortcode": self.sender_id,
                "serviceId": 0
            }

            logger.info(f"Sending SMS to {phone}")

            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )

            # Handle non-JSON responses gracefully
            try:
                data = response.json()
            except Exception:
                logger.warning(f"Qorami SMS: Non-JSON response (status {response.status_code})")
                return {
                    'success': False,
                    'error': f'Invalid response from SMS API (HTTP {response.status_code})',
                    'raw_response': response.text[:200] if response.text else 'Empty response'
                }

            if response.status_code == 200 and data.get('status_code') == '1000':
                return {
                    'success': True,
                    'message_id': data.get('message_id'),
                    'status': data.get('status_desc'),
                    'balance': data.get('credit_balance')
                }
            else:
                error_msg = data.get('status_desc') or data.get('message') or 'SMS send failed'
                logger.warning(f"Qorami SMS failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'details': data
                }

        except requests.Timeout:
            logger.warning(f"Qorami SMS timeout for {phone}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.warning(f"Qorami SMS request failed: {e}")
            return {'success': False, 'error': str(e)}

    def send_bulk_sms(
        self,
        recipients: List[Dict]
    ) -> Dict:
        """
        Send bulk SMS messages.

        Args:
            recipients: List of dicts with keys:
                - phone: Recipient phone number
                - message: SMS content

        Returns:
            Dict with success status and batch details
        """
        results = {
            'success': True,
            'total': len(recipients),
            'sent': 0,
            'failed': 0,
            'details': []
        }

        for recipient in recipients:
            result = self.send_sms(
                phone=recipient.get('phone', ''),
                message=recipient.get('message', '')
            )

            if result.get('success'):
                results['sent'] += 1
            else:
                results['failed'] += 1

            results['details'].append({
                'phone': recipient.get('phone'),
                'result': result
            })

        if results['failed'] > 0:
            results['success'] = results['sent'] > 0  # Partial success

        return results

    def send_payment_notification(
        self,
        phone: str,
        employee_name: str,
        amount: float,
        company_name: str = "Your Employer"
    ) -> Dict:
        """
        Send a payment notification SMS.

        Args:
            phone: Recipient phone number
            employee_name: Employee's name
            amount: Payment amount in KES
            company_name: Company name

        Returns:
            Dict with success status
        """
        message = (
            f"Dear {employee_name}, your salary of KES {amount:,.2f} "
            f"has been sent to your M-Pesa by {company_name}. "
            f"Thank you for your service."
        )

        return self.send_sms(phone, message)

    def get_balance(self) -> Dict:
        """Get SMS credit balance."""
        try:
            if not self.api_key:
                return {'success': False, 'error': 'Qorami API key not configured'}

            url = f"{self.BASE_URL}/v1/balance"

            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=30
            )

            data = response.json()

            if response.status_code == 200:
                return {
                    'success': True,
                    'balance': data.get('credit_balance') or data.get('balance'),
                    'details': data
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message') or 'Balance query failed'
                }

        except requests.RequestException as e:
            logger.exception("Qorami balance query failed")
            return {'success': False, 'error': str(e)}

    def get_delivery_status(self, message_id: str) -> Dict:
        """Get delivery status of a sent message."""
        try:
            if not self.api_key:
                return {'success': False, 'error': 'Qorami API key not configured'}

            url = f"{self.BASE_URL}/dlr/receive"

            params = {
                'message_id': message_id
            }

            response = requests.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=30
            )

            data = response.json()

            return {
                'success': True,
                'status': data
            }

        except requests.RequestException as e:
            logger.exception("Qorami DLR query failed")
            return {'success': False, 'error': str(e)}

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to 254XXXXXXXXX format."""
        if not phone:
            return ''

        phone = str(phone).replace(' ', '').replace('-', '').replace('+', '')

        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif phone.startswith('7') or phone.startswith('1'):
            phone = '254' + phone
        elif not phone.startswith('254'):
            phone = '254' + phone

        # Validate length (should be 12 digits for Kenya)
        if len(phone) != 12:
            logger.warning(f"Invalid phone number length: {phone}")
            return ''

        return phone
