import requests
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from django.conf import settings

logger = logging.getLogger(__name__)


class PesaPalService:
    """
    PesaPal payment gateway integration service.
    Handles Bank EFT, M-Pesa, and Airtel Money disbursements for payroll.

    Credentials are loaded from Django settings (environment variables):
    - PESAPAL_CONSUMER_KEY
    - PESAPAL_CONSUMER_SECRET
    - PESAPAL_IPN_ID
    - PESAPAL_SANDBOX

    Supports:
    - Individual payments (M-Pesa, Airtel Money, Bank EFT)
    - Bulk disbursements for efficient payroll processing
    - IPN (Instant Payment Notification) registration and handling
    - Transaction status checking
    """

    SANDBOX_URL = 'https://cybqa.pesapal.com/pesapalv3'
    PRODUCTION_URL = 'https://pay.pesapal.com/v3'

    # Token expires in 5 minutes, refresh at 4 minutes
    TOKEN_REFRESH_BUFFER = 240  # seconds

    def __init__(
        self,
        consumer_key: str = None,
        consumer_secret: str = None,
        ipn_id: str = None,
        sandbox: bool = None
    ):
        """
        Initialize PesaPal service.

        Args:
            consumer_key: PesaPal consumer key (defaults to settings.PESAPAL_CONSUMER_KEY)
            consumer_secret: PesaPal consumer secret (defaults to settings.PESAPAL_CONSUMER_SECRET)
            ipn_id: PesaPal IPN ID (defaults to settings.PESAPAL_IPN_ID)
            sandbox: Use sandbox environment (defaults to settings.PESAPAL_SANDBOX)
        """
        self.consumer_key = consumer_key or getattr(settings, 'PESAPAL_CONSUMER_KEY', '')
        self.consumer_secret = consumer_secret or getattr(settings, 'PESAPAL_CONSUMER_SECRET', '')
        self.ipn_id = ipn_id or getattr(settings, 'PESAPAL_IPN_ID', '')
        self.sandbox = sandbox if sandbox is not None else getattr(settings, 'PESAPAL_SANDBOX', True)
        self.base_url = self.SANDBOX_URL if self.sandbox else self.PRODUCTION_URL
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def _get_access_token(self) -> str:
        """Authenticate and get access token with expiry handling"""
        # Check if token is still valid
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry:
                return self._access_token

        url = f"{self.base_url}/api/Auth/RequestToken"
        payload = {
            "consumer_key": self.consumer_key,
            "consumer_secret": self.consumer_secret
        }

        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            self._access_token = data.get('token')

            # Token typically expires in 5 minutes
            expires_in = data.get('expiryDate', '')
            if expires_in:
                try:
                    self._token_expiry = datetime.fromisoformat(expires_in.replace('Z', '+00:00'))
                except ValueError:
                    # Fallback: set expiry to 4 minutes from now
                    self._token_expiry = datetime.now() + timedelta(seconds=self.TOKEN_REFRESH_BUFFER)
            else:
                self._token_expiry = datetime.now() + timedelta(seconds=self.TOKEN_REFRESH_BUFFER)

            return self._access_token

        except requests.RequestException as e:
            logger.exception("Failed to get PesaPal access token")
            raise

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authorization"""
        token = self._get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def register_ipn(self, callback_url: str, ipn_notification_type: str = "GET") -> Dict:
        """
        Register IPN URL with PesaPal.
        This must be called once to get an IPN ID before processing payments.

        Args:
            callback_url: Your webhook URL to receive payment notifications
            ipn_notification_type: "GET" or "POST"

        Returns:
            Dict with ipn_id on success
        """
        try:
            url = f"{self.base_url}/api/URLSetup/RegisterIPN"
            payload = {
                "url": callback_url,
                "ipn_notification_type": ipn_notification_type
            }

            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=30)
            response.raise_for_status()

            data = response.json()

            if data.get('status') == '200':
                return {
                    'success': True,
                    'ipn_id': data.get('ipn_id'),
                    'url': data.get('url')
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message', 'IPN registration failed')
                }

        except requests.RequestException as e:
            logger.exception("Failed to register IPN")
            return {
                'success': False,
                'error': str(e)
            }

    def get_registered_ipns(self) -> Dict:
        """Get list of registered IPN URLs"""
        try:
            url = f"{self.base_url}/api/URLSetup/GetIpnList"
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.exception("Failed to get IPN list")
            return {'error': str(e)}

    def send_mpesa(
        self,
        phone: str,
        amount: float,
        reference: str,
        description: str = "Salary Payment",
        callback_url: str = ""
    ) -> Dict:
        """
        Send payment via M-Pesa B2C (Business to Customer).

        Args:
            phone: M-Pesa phone number (format: 254XXXXXXXXX or 07XXXXXXXX)
            amount: Amount in KES
            reference: Unique payment reference
            description: Payment description
            callback_url: Optional callback URL (uses IPN if not provided)

        Returns:
            Dict with success status, order_tracking_id, and reference or error
        """
        try:
            phone = self._normalize_phone(phone)

            if not phone:
                return {'success': False, 'error': 'Invalid phone number'}

            url = f"{self.base_url}/api/Transactions/SubmitOrderRequest"
            payload = {
                "id": reference,
                "currency": "KES",
                "amount": amount,
                "description": description,
                "callback_url": callback_url,
                "notification_id": self.ipn_id,
                "branch": "Payroll",
                "billing_address": {
                    "phone_number": phone,
                    "country_code": "KE"
                }
            }

            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=60)
            response.raise_for_status()

            data = response.json()

            if data.get('status') == '200':
                return {
                    'success': True,
                    'order_tracking_id': data.get('order_tracking_id'),
                    'merchant_reference': data.get('merchant_reference'),
                    'reference': data.get('order_tracking_id')
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message', 'M-Pesa payment failed'),
                    'error_code': data.get('status')
                }

        except requests.Timeout:
            logger.error(f"M-Pesa payment timeout for {reference}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception(f"M-Pesa payment failed for {reference}")
            return {'success': False, 'error': str(e)}

    def send_airtel(
        self,
        phone: str,
        amount: float,
        reference: str,
        description: str = "Salary Payment",
        callback_url: str = ""
    ) -> Dict:
        """
        Send payment via Airtel Money.

        Args:
            phone: Airtel phone number (format: 254XXXXXXXXX)
            amount: Amount in KES
            reference: Unique payment reference
            description: Payment description
            callback_url: Optional callback URL

        Returns:
            Dict with success status and reference or error
        """
        try:
            phone = self._normalize_phone(phone)

            if not phone:
                return {'success': False, 'error': 'Invalid phone number'}

            url = f"{self.base_url}/api/Transactions/SubmitOrderRequest"
            payload = {
                "id": reference,
                "currency": "KES",
                "amount": amount,
                "description": description,
                "callback_url": callback_url,
                "notification_id": self.ipn_id,
                "branch": "Payroll",
                "billing_address": {
                    "phone_number": phone,
                    "country_code": "KE"
                }
            }

            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=60)
            response.raise_for_status()

            data = response.json()

            if data.get('status') == '200':
                return {
                    'success': True,
                    'order_tracking_id': data.get('order_tracking_id'),
                    'merchant_reference': data.get('merchant_reference'),
                    'reference': data.get('order_tracking_id')
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message', 'Airtel payment failed'),
                    'error_code': data.get('status')
                }

        except requests.Timeout:
            logger.error(f"Airtel payment timeout for {reference}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception(f"Airtel payment failed for {reference}")
            return {'success': False, 'error': str(e)}

    def send_bank_eft(
        self,
        bank_name: str,
        account_number: str,
        amount: float,
        reference: str,
        account_name: str = "",
        branch_code: str = "",
        description: str = "Salary Payment",
        callback_url: str = ""
    ) -> Dict:
        """
        Send payment via Bank EFT.

        Args:
            bank_name: Name of the bank
            account_number: Bank account number
            amount: Amount in KES
            reference: Unique payment reference
            account_name: Account holder name
            branch_code: Bank branch code (optional)
            description: Payment description
            callback_url: Optional callback URL

        Returns:
            Dict with success status and reference or error
        """
        try:
            bank_code = self._get_bank_code(bank_name)

            if not bank_code:
                return {'success': False, 'error': f'Unknown bank: {bank_name}'}

            if not account_number:
                return {'success': False, 'error': 'Account number required'}

            url = f"{self.base_url}/api/Transactions/SubmitOrderRequest"
            payload = {
                "id": reference,
                "currency": "KES",
                "amount": amount,
                "description": description,
                "callback_url": callback_url,
                "notification_id": self.ipn_id,
                "branch": "Payroll",
                "billing_address": {
                    "country_code": "KE",
                    "first_name": account_name.split()[0] if account_name else "",
                    "last_name": " ".join(account_name.split()[1:]) if account_name and len(account_name.split()) > 1 else ""
                },
                "account_number": account_number,
                "bank_code": bank_code
            }

            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=60)
            response.raise_for_status()

            data = response.json()

            if data.get('status') == '200':
                return {
                    'success': True,
                    'order_tracking_id': data.get('order_tracking_id'),
                    'merchant_reference': data.get('merchant_reference'),
                    'reference': data.get('order_tracking_id')
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message', 'Bank EFT payment failed'),
                    'error_code': data.get('status')
                }

        except requests.Timeout:
            logger.error(f"Bank EFT payment timeout for {reference}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception(f"Bank EFT payment failed for {reference}")
            return {'success': False, 'error': str(e)}

    def submit_bulk_disbursement(
        self,
        disbursements: List[Dict],
        batch_reference: str,
        description: str = "Payroll Disbursement"
    ) -> Dict:
        """
        Submit bulk disbursement for payroll processing.
        More efficient than individual payments for large payrolls.

        Args:
            disbursements: List of payment dictionaries with keys:
                - reference: Unique payment reference
                - amount: Amount in KES
                - payment_method: 'mpesa', 'airtel', or 'bank'
                - phone: Phone number (for mobile money)
                - bank_code: Bank code (for bank transfers)
                - account_number: Account number (for bank transfers)
                - account_name: Account holder name
            batch_reference: Unique batch reference
            description: Batch description

        Returns:
            Dict with batch_id and individual payment statuses
        """
        try:
            url = f"{self.base_url}/api/Transactions/SubmitBulkDisbursement"

            payments = []
            for d in disbursements:
                payment = {
                    "unique_id": d['reference'],
                    "currency": "KES",
                    "amount": d['amount'],
                    "description": description
                }

                if d['payment_method'] in ['mpesa', 'airtel']:
                    payment['phone_number'] = self._normalize_phone(d.get('phone', ''))
                else:  # bank
                    payment['bank_code'] = d.get('bank_code') or self._get_bank_code(d.get('bank_name', ''))
                    payment['account_number'] = d.get('account_number', '')
                    payment['account_name'] = d.get('account_name', '')

                payments.append(payment)

            payload = {
                "batch_reference": batch_reference,
                "notification_id": self.ipn_id,
                "disbursements": payments
            }

            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=120)
            response.raise_for_status()

            data = response.json()

            if data.get('status') == '200':
                return {
                    'success': True,
                    'batch_id': data.get('batch_id'),
                    'batch_reference': batch_reference,
                    'total_count': len(payments),
                    'disbursements': data.get('disbursements', [])
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message', 'Bulk disbursement failed'),
                    'error_code': data.get('status')
                }

        except requests.Timeout:
            logger.error(f"Bulk disbursement timeout for batch {batch_reference}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception(f"Bulk disbursement failed for batch {batch_reference}")
            return {'success': False, 'error': str(e)}

    def get_transaction_status(self, order_tracking_id: str) -> Dict:
        """
        Get status of a transaction.

        Args:
            order_tracking_id: PesaPal order tracking ID

        Returns:
            Dict with transaction status details:
            - payment_status_description: COMPLETED, PENDING, FAILED, INVALID
            - amount: Transaction amount
            - created_date: Transaction creation date
            - payment_method: Payment method used
            - confirmation_code: Payment confirmation code
        """
        try:
            url = f"{self.base_url}/api/Transactions/GetTransactionStatus"
            params = {"orderTrackingId": order_tracking_id}

            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            response.raise_for_status()

            data = response.json()

            return {
                'success': True,
                'order_tracking_id': order_tracking_id,
                'payment_status': data.get('payment_status_description', 'UNKNOWN'),
                'status_code': data.get('status_code'),
                'amount': data.get('amount'),
                'currency': data.get('currency'),
                'payment_method': data.get('payment_method'),
                'confirmation_code': data.get('confirmation_code'),
                'payment_account': data.get('payment_account'),
                'created_date': data.get('created_date'),
                'message': data.get('message')
            }

        except requests.RequestException as e:
            logger.exception(f"Failed to get transaction status for {order_tracking_id}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_bulk_disbursement_status(self, batch_id: str) -> Dict:
        """
        Get status of a bulk disbursement batch.

        Args:
            batch_id: PesaPal batch ID

        Returns:
            Dict with batch status and individual payment statuses
        """
        try:
            url = f"{self.base_url}/api/Transactions/GetBulkDisbursementStatus"
            params = {"batchId": batch_id}

            response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            logger.exception(f"Failed to get bulk disbursement status for {batch_id}")
            return {'error': str(e)}

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to 254XXXXXXXXX format"""
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

    def _get_bank_code(self, bank_name: str) -> str:
        """
        Get bank code from bank name.
        Complete list of Kenyan bank codes.
        """
        if not bank_name:
            return ''

        bank_codes = {
            # Major banks
            'kcb': '01',
            'kenya commercial bank': '01',
            'standard chartered': '02',
            'scb': '02',
            'barclays': '03',
            'absa': '03',
            'absa bank': '03',
            'cooperative bank': '11',
            'coop bank': '11',
            'co-operative bank': '11',
            'equity': '68',
            'equity bank': '68',
            'ncba': '07',
            'ncba bank': '07',
            'nic': '07',
            'cba': '07',

            # Other commercial banks
            'family bank': '70',
            'dtb': '63',
            'diamond trust': '63',
            'diamond trust bank': '63',
            'stanbic': '31',
            'stanbic bank': '31',
            'im bank': '57',
            'i&m bank': '57',
            'i&m': '57',
            'gtbank': '53',
            'gt bank': '53',
            'guaranty trust': '53',
            'prime bank': '10',
            'credit bank': '25',
            'victoria commercial bank': '54',
            'victoria bank': '54',
            'guardian bank': '55',
            'sidian bank': '66',
            'sidian': '66',
            'm-oriental bank': '14',
            'oriental bank': '14',
            'bank of baroda': '06',
            'baroda': '06',
            'bank of india': '05',
            'citibank': '16',
            'citi': '16',
            'habib bank': '08',
            'hbl': '08',
            'national bank': '12',
            'national bank of kenya': '12',
            'nbk': '12',
            'abc bank': '35',
            'african banking corporation': '35',
            'consolidated bank': '23',
            'development bank of kenya': '59',
            'dbk': '59',
            'dubai islamic bank': '75',
            'dib': '75',
            'ecobank': '43',
            'eco bank': '43',
            'first community bank': '74',
            'fcb': '74',
            'gulf african bank': '72',
            'gab': '72',
            'housing finance': '61',
            'hfc': '61',
            'hf group': '61',
            'middle east bank': '18',
            'meb': '18',
            'paramount bank': '50',
            'spire bank': '49',
            'transnational bank': '26',
            'uba': '76',
            'united bank for africa': '76',
            'mayfair bank': '65',
            'kingdom bank': '51',
            'access bank': '84',

            # Microfinance banks
            'kenya women microfinance': '78',
            'kwft': '78',
            'faulu microfinance': '79',
            'faulu': '79',
            'century microfinance': '80',
            'sumac microfinance': '81',
            'rafiki microfinance': '82',
            'rafiki': '82',
            'choice microfinance': '83',
            'caritas microfinance': '85',
            'daraja microfinance': '86',
            'uwezo microfinance': '87',
            'maisha microfinance': '88',
        }

        bank_lower = bank_name.lower().strip()

        # Exact match first
        if bank_lower in bank_codes:
            return bank_codes[bank_lower]

        # Partial match
        for name, code in bank_codes.items():
            if name in bank_lower or bank_lower in name:
                return code

        logger.warning(f"Bank code not found for: {bank_name}")
        return ''

    @staticmethod
    def map_payment_status(pesapal_status: str) -> str:
        """
        Map PesaPal payment status to internal status.

        PesaPal statuses: COMPLETED, PENDING, FAILED, INVALID
        Internal statuses: paid, processing, failed, pending
        """
        status_map = {
            'COMPLETED': 'paid',
            'PENDING': 'processing',
            'FAILED': 'failed',
            'INVALID': 'failed',
            'REVERSED': 'failed',
        }
        return status_map.get(pesapal_status.upper(), 'processing')
