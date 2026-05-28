"""
Africa's Talking SMS API Integration Service.

Sends SMS notifications for payroll disbursements.

To set up:
1. Register at https://africastalking.com/
2. Get your API key from Settings → API Key
3. For sandbox testing, username is always 'sandbox'

Environment variables required:
- AT_USERNAME: Your Africa's Talking username ('sandbox' for testing)
- AT_API_KEY: Your Africa's Talking API key
- AT_SENDER_ID: Optional sender ID (leave empty for sandbox)
"""

import requests
import logging
from typing import Dict, List
from django.conf import settings

logger = logging.getLogger(__name__)


class AfricasTalkingSMSService:
    """
    Africa's Talking SMS service for sending payment notifications.

    Docs: https://developers.africastalking.com/docs/sms/overview
    """

    SANDBOX_URL = 'https://api.sandbox.africastalking.com/version1/messaging'
    PRODUCTION_URL = 'https://api.africastalking.com/version1/messaging'

    def __init__(
        self,
        username: str = None,
        api_key: str = None,
        sender_id: str = None
    ):
        """Initialize Africa's Talking SMS service."""
        self.username = username or getattr(settings, 'AT_USERNAME', 'sandbox')
        self.api_key = api_key or getattr(settings, 'AT_API_KEY', '')
        self.sender_id = sender_id or getattr(settings, 'AT_SENDER_ID', '')

        # Use sandbox URL if username is 'sandbox'
        self.is_sandbox = self.username.lower() == 'sandbox'
        self.base_url = self.SANDBOX_URL if self.is_sandbox else self.PRODUCTION_URL

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with API key."""
        return {
            'apiKey': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded',
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
            phone: Recipient phone number (format: +254XXXXXXXXX)
            message: SMS content

        Returns:
            Dict with success status and message details
        """
        try:
            phone = self._normalize_phone(phone)

            if not phone:
                return {'success': False, 'error': 'Invalid phone number'}

            if not self.api_key:
                return {'success': False, 'error': 'Africa\'s Talking API key not configured'}

            # Build form data
            data = {
                'username': self.username,
                'to': phone,
                'message': message
            }

            # Add sender ID for production (not allowed in sandbox)
            if self.sender_id and not self.is_sandbox:
                data['from'] = self.sender_id

            logger.info(f"Sending SMS to {phone} via Africa's Talking ({'sandbox' if self.is_sandbox else 'production'})")

            response = requests.post(
                self.base_url,
                data=data,
                headers=self._get_headers(),
                timeout=30
            )

            # Parse response
            try:
                result = response.json()
            except Exception:
                logger.warning(f"AT SMS: Non-JSON response (status {response.status_code})")
                return {
                    'success': False,
                    'error': f'Invalid response (HTTP {response.status_code})',
                    'raw_response': response.text[:200]
                }

            # Check for success
            sms_data = result.get('SMSMessageData', {})
            recipients = sms_data.get('Recipients', [])

            if recipients:
                recipient = recipients[0]
                status_code = recipient.get('statusCode')

                # Status codes: 100=Processed, 101=Sent, 102=Queued
                if status_code in [100, 101, 102]:
                    return {
                        'success': True,
                        'message_id': recipient.get('messageId'),
                        'status': recipient.get('status'),
                        'cost': recipient.get('cost'),
                        'phone': recipient.get('number')
                    }
                else:
                    return {
                        'success': False,
                        'error': recipient.get('status', 'Send failed'),
                        'status_code': status_code
                    }
            else:
                error_message = sms_data.get('Message', 'Unknown error')
                return {
                    'success': False,
                    'error': error_message,
                    'details': result
                }

        except requests.Timeout:
            logger.warning(f"AT SMS timeout for {phone}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.warning(f"AT SMS request failed: {e}")
            return {'success': False, 'error': str(e)}

    def send_bulk_sms(
        self,
        recipients: List[Dict]
    ) -> Dict:
        """
        Send bulk SMS messages.

        Args:
            recipients: List of dicts with 'phone' and 'message' keys

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

        results['success'] = results['sent'] > 0
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

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to +254XXXXXXXXX format."""
        if not phone:
            return ''

        phone = str(phone).replace(' ', '').replace('-', '')

        # Remove leading + if present for processing
        if phone.startswith('+'):
            phone = phone[1:]

        # Convert to international format
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif phone.startswith('7') or phone.startswith('1'):
            phone = '254' + phone

        # Add + prefix
        if not phone.startswith('+'):
            phone = '+' + phone

        # Validate length (+254XXXXXXXXX = 13 characters)
        if len(phone) != 13:
            logger.warning(f"Invalid phone number length: {phone}")
            return ''

        return phone

    def get_balance(self) -> Dict:
        """Get account balance (not available via simple API)."""
        return {'success': False, 'error': 'Use dashboard to check balance'}
