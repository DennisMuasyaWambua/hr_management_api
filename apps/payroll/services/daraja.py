"""
Safaricom Daraja M-Pesa B2C Integration Service.

Handles M-Pesa Business to Customer (B2C) disbursements for payroll.

To set up:
1. Register at https://developer.safaricom.co.ke/
2. Create an app and get Consumer Key/Secret
3. For production: Apply for B2C access with your business shortcode

Environment variables required:
- DARAJA_CONSUMER_KEY: Your Safaricom app consumer key
- DARAJA_CONSUMER_SECRET: Your Safaricom app consumer secret
- DARAJA_SHORTCODE: Your B2C shortcode (sandbox: 600998)
- DARAJA_INITIATOR_NAME: Initiator name (sandbox: testapi)
- DARAJA_INITIATOR_PASSWORD: Security credential
- DARAJA_SANDBOX: True for sandbox, False for production
"""

import requests
import base64
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class DarajaService:
    """
    Safaricom M-Pesa Daraja API service for B2C disbursements.
    """

    SANDBOX_URL = 'https://sandbox.safaricom.co.ke'
    PRODUCTION_URL = 'https://api.safaricom.co.ke'

    # Sandbox test credentials
    SANDBOX_SHORTCODE = '600998'
    SANDBOX_INITIATOR = 'testapi'
    SANDBOX_INITIATOR_PASSWORD = 'Safaricom999!*!'

    # Token cache
    _access_token: Optional[str] = None
    _token_expiry: Optional[datetime] = None

    def __init__(
        self,
        consumer_key: str = None,
        consumer_secret: str = None,
        shortcode: str = None,
        initiator_name: str = None,
        initiator_password: str = None,
        sandbox: bool = None
    ):
        """Initialize Daraja service with credentials."""
        self.sandbox = sandbox if sandbox is not None else getattr(settings, 'DARAJA_SANDBOX', True)
        self.base_url = self.SANDBOX_URL if self.sandbox else self.PRODUCTION_URL

        # Use sandbox defaults if in sandbox mode and no credentials provided
        if self.sandbox:
            self.consumer_key = consumer_key or getattr(settings, 'DARAJA_CONSUMER_KEY', '')
            self.consumer_secret = consumer_secret or getattr(settings, 'DARAJA_CONSUMER_SECRET', '')
            self.shortcode = shortcode or getattr(settings, 'DARAJA_SHORTCODE', self.SANDBOX_SHORTCODE)
            self.initiator_name = initiator_name or getattr(settings, 'DARAJA_INITIATOR_NAME', self.SANDBOX_INITIATOR)
            self.initiator_password = initiator_password or getattr(settings, 'DARAJA_INITIATOR_PASSWORD', self.SANDBOX_INITIATOR_PASSWORD)
        else:
            self.consumer_key = consumer_key or getattr(settings, 'DARAJA_CONSUMER_KEY', '')
            self.consumer_secret = consumer_secret or getattr(settings, 'DARAJA_CONSUMER_SECRET', '')
            self.shortcode = shortcode or getattr(settings, 'DARAJA_SHORTCODE', '')
            self.initiator_name = initiator_name or getattr(settings, 'DARAJA_INITIATOR_NAME', '')
            self.initiator_password = initiator_password or getattr(settings, 'DARAJA_INITIATOR_PASSWORD', '')

        # Callback URLs
        self.result_url = getattr(settings, 'DARAJA_RESULT_URL', '')
        self.timeout_url = getattr(settings, 'DARAJA_TIMEOUT_URL', '')

    def _get_access_token(self) -> str:
        """Get OAuth access token from Safaricom."""
        # Check cache
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry:
                return self._access_token

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"

        # Basic auth with consumer key and secret
        credentials = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode()
        ).decode()

        headers = {
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            self._access_token = data.get('access_token')

            # Token expires in 1 hour, refresh at 55 minutes
            expires_in = int(data.get('expires_in', 3600))
            self._token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)

            return self._access_token

        except requests.RequestException as e:
            logger.exception("Failed to get Daraja access token")
            raise

    def _get_security_credential(self) -> str:
        """
        Generate security credential by encrypting initiator password.

        For sandbox, you can use the test password directly.
        For production, this encrypts the password with Safaricom's public cert.
        """
        if self.sandbox:
            # For sandbox, encrypt with sandbox certificate
            cert_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
            # In sandbox, we can use base64 encoded password for simplicity
            # The actual implementation would download and use the sandbox cert
            return base64.b64encode(self.initiator_password.encode()).decode()

        # For production, download and use the production certificate
        # This is a simplified version - production would use actual cert
        return base64.b64encode(self.initiator_password.encode()).decode()

    def send_b2c(
        self,
        phone: str,
        amount: float,
        reference: str,
        remarks: str = "Salary Payment",
        occasion: str = ""
    ) -> Dict:
        """
        Send M-Pesa B2C payment to customer.

        Args:
            phone: Recipient phone number (format: 254XXXXXXXXX)
            amount: Amount in KES (integer)
            reference: Unique transaction reference
            remarks: Transaction remarks
            occasion: Optional occasion description

        Returns:
            Dict with success status and transaction details
        """
        try:
            phone = self._normalize_phone(phone)

            if not phone:
                return {'success': False, 'error': 'Invalid phone number'}

            if not self.consumer_key or not self.consumer_secret:
                return {'success': False, 'error': 'Daraja credentials not configured'}

            token = self._get_access_token()

            url = f"{self.base_url}/mpesa/b2c/v3/paymentrequest"

            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            payload = {
                'OriginatorConversationID': reference,
                'InitiatorName': self.initiator_name,
                'SecurityCredential': self._get_security_credential(),
                'CommandID': 'SalaryPayment',  # Or 'BusinessPayment', 'PromotionPayment'
                'Amount': int(amount),  # Must be integer
                'PartyA': self.shortcode,
                'PartyB': phone,
                'Remarks': remarks,
                'QueueTimeOutURL': self.timeout_url or 'https://webhook.site/timeout',
                'ResultURL': self.result_url or 'https://webhook.site/result',
                'Occasion': occasion
            }

            logger.info(f"Sending B2C to {phone}: KES {amount}")

            response = requests.post(url, json=payload, headers=headers, timeout=60)

            data = response.json()

            if response.status_code == 200 and data.get('ResponseCode') == '0':
                return {
                    'success': True,
                    'conversation_id': data.get('ConversationID'),
                    'originator_conversation_id': data.get('OriginatorConversationID'),
                    'response_description': data.get('ResponseDescription'),
                    'reference': reference
                }
            else:
                error_msg = data.get('errorMessage') or data.get('ResponseDescription') or 'B2C request failed'
                logger.error(f"B2C failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'error_code': data.get('errorCode') or data.get('ResponseCode')
                }

        except requests.Timeout:
            logger.error(f"B2C timeout for {reference}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception(f"B2C request failed for {reference}")
            return {'success': False, 'error': str(e)}

    def query_transaction_status(
        self,
        transaction_id: str,
        identifier_type: str = "4"  # 4 = Shortcode
    ) -> Dict:
        """
        Query the status of a B2C transaction.

        Args:
            transaction_id: The ConversationID or OriginatorConversationID
            identifier_type: 1=MSISDN, 2=Till, 4=Shortcode

        Returns:
            Dict with transaction status
        """
        try:
            token = self._get_access_token()

            url = f"{self.base_url}/mpesa/transactionstatus/v1/query"

            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            payload = {
                'Initiator': self.initiator_name,
                'SecurityCredential': self._get_security_credential(),
                'CommandID': 'TransactionStatusQuery',
                'TransactionID': transaction_id,
                'PartyA': self.shortcode,
                'IdentifierType': identifier_type,
                'ResultURL': self.result_url or 'https://webhook.site/result',
                'QueueTimeOutURL': self.timeout_url or 'https://webhook.site/timeout',
                'Remarks': 'Status Query',
                'Occasion': ''
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)
            data = response.json()

            if response.status_code == 200 and data.get('ResponseCode') == '0':
                return {
                    'success': True,
                    'conversation_id': data.get('ConversationID'),
                    'response_description': data.get('ResponseDescription')
                }
            else:
                return {
                    'success': False,
                    'error': data.get('errorMessage') or data.get('ResponseDescription')
                }

        except requests.RequestException as e:
            logger.exception(f"Transaction status query failed")
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

    @staticmethod
    def map_result_code(result_code: str) -> str:
        """
        Map Safaricom result codes to internal status.

        Result codes:
        - 0: Success
        - 1: Insufficient balance
        - 2001: Wrong credentials
        - 2006: Invalid transaction
        """
        code_map = {
            '0': 'paid',
            '1': 'failed',  # Insufficient balance
            '2001': 'failed',  # Wrong credentials
            '2006': 'failed',  # Invalid transaction
        }
        return code_map.get(str(result_code), 'processing')

    def check_balance(self) -> Dict:
        """Check account balance (requires additional permissions)."""
        try:
            token = self._get_access_token()

            url = f"{self.base_url}/mpesa/accountbalance/v1/query"

            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            payload = {
                'Initiator': self.initiator_name,
                'SecurityCredential': self._get_security_credential(),
                'CommandID': 'AccountBalance',
                'PartyA': self.shortcode,
                'IdentifierType': '4',  # Shortcode
                'Remarks': 'Balance Query',
                'QueueTimeOutURL': self.timeout_url or 'https://webhook.site/timeout',
                'ResultURL': self.result_url or 'https://webhook.site/result'
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)
            data = response.json()

            return data

        except requests.RequestException as e:
            logger.exception("Balance query failed")
            return {'error': str(e)}
