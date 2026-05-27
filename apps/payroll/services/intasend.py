"""
IntaSend M-Pesa B2C Integration Service.

Handles M-Pesa Business to Customer (B2C) disbursements for payroll.

To set up:
1. Register at https://intasend.com/
2. Get your API keys from the dashboard
3. For production: Complete KYC verification

Environment variables required:
- INTASEND_PUBLISHABLE_KEY: Your IntaSend publishable key
- INTASEND_SECRET_KEY: Your IntaSend secret key
- INTASEND_SANDBOX: True for sandbox, False for production
"""

import requests
import logging
from typing import Dict, List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class IntaSendService:
    """
    IntaSend payment service for M-Pesa B2C disbursements.

    Documentation: https://developers.intasend.com/
    """

    SANDBOX_URL = 'https://sandbox.intasend.com/api/v1'
    PRODUCTION_URL = 'https://payment.intasend.com/api/v1'

    def __init__(
        self,
        publishable_key: str = None,
        secret_key: str = None,
        sandbox: bool = None
    ):
        """Initialize IntaSend service with credentials."""
        self.sandbox = sandbox if sandbox is not None else getattr(settings, 'INTASEND_SANDBOX', True)
        self.base_url = self.SANDBOX_URL if self.sandbox else self.PRODUCTION_URL

        self.publishable_key = publishable_key or getattr(settings, 'INTASEND_PUBLISHABLE_KEY', '')
        self.secret_key = secret_key or getattr(settings, 'INTASEND_SECRET_KEY', '')

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authorization."""
        return {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def send_mpesa(
        self,
        phone: str,
        amount: float,
        reference: str,
        name: str = "Employee",
        narrative: str = "Salary Payment"
    ) -> Dict:
        """
        Send M-Pesa B2C payment to a phone number.

        Args:
            phone: Recipient phone number (format: 254XXXXXXXXX or 07XXXXXXXX)
            amount: Amount in KES
            reference: Unique payment reference
            name: Recipient name
            narrative: Payment description

        Returns:
            Dict with success status and transaction details
        """
        try:
            phone = self._normalize_phone(phone)

            if not phone:
                return {'success': False, 'error': 'Invalid phone number'}

            if not self.secret_key:
                return {'success': False, 'error': 'IntaSend credentials not configured'}

            url = f"{self.base_url}/send-money/initiate/"

            payload = {
                "currency": "KES",
                "provider": "MPESA-B2C",
                "transactions": [
                    {
                        "account": phone,
                        "amount": str(amount),
                        "narrative": narrative,
                        "name": name,
                        "reference": reference
                    }
                ]
            }

            logger.info(f"Sending M-Pesa B2C to {phone}: KES {amount}")

            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=60
            )

            data = response.json()

            if response.status_code in [200, 201]:
                # Check if the request was accepted
                if data.get('status') == 'Preview and approve':
                    # Need to approve the transaction
                    tracking_id = data.get('tracking_id')
                    if tracking_id:
                        return self._approve_transaction(tracking_id, reference)

                return {
                    'success': True,
                    'tracking_id': data.get('tracking_id'),
                    'reference': reference,
                    'status': data.get('status'),
                    'message': 'Payment initiated successfully'
                }
            else:
                error_msg = data.get('message') or data.get('error') or data.get('detail') or 'Payment request failed'
                logger.error(f"IntaSend B2C failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'details': data
                }

        except requests.Timeout:
            logger.error(f"IntaSend B2C timeout for {reference}")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception(f"IntaSend B2C request failed for {reference}")
            return {'success': False, 'error': str(e)}

    def _approve_transaction(self, tracking_id: str, reference: str) -> Dict:
        """
        Approve a pending transaction.

        IntaSend requires approval after initiating a send-money request.
        """
        try:
            url = f"{self.base_url}/send-money/approve/"

            payload = {
                "tracking_id": tracking_id
            }

            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=60
            )

            data = response.json()

            if response.status_code in [200, 201]:
                return {
                    'success': True,
                    'tracking_id': tracking_id,
                    'reference': reference,
                    'status': data.get('status', 'approved'),
                    'message': 'Payment approved and processing'
                }
            else:
                error_msg = data.get('message') or data.get('error') or 'Approval failed'
                return {
                    'success': False,
                    'error': error_msg,
                    'tracking_id': tracking_id
                }

        except requests.RequestException as e:
            logger.exception(f"IntaSend approval failed for {tracking_id}")
            return {'success': False, 'error': str(e)}

    def send_bulk_mpesa(
        self,
        transactions: List[Dict],
        narrative: str = "Salary Payment"
    ) -> Dict:
        """
        Send bulk M-Pesa B2C payments.

        Args:
            transactions: List of dicts with keys:
                - phone: Recipient phone number
                - amount: Amount in KES
                - reference: Unique reference
                - name: Recipient name (optional)
            narrative: Payment description

        Returns:
            Dict with success status and batch details
        """
        try:
            if not self.secret_key:
                return {'success': False, 'error': 'IntaSend credentials not configured'}

            url = f"{self.base_url}/send-money/initiate/"

            # Format transactions for IntaSend
            formatted_transactions = []
            for txn in transactions:
                phone = self._normalize_phone(txn.get('phone', ''))
                if phone:
                    formatted_transactions.append({
                        "account": phone,
                        "amount": str(txn.get('amount', 0)),
                        "narrative": narrative,
                        "name": txn.get('name', 'Employee'),
                        "reference": txn.get('reference', '')
                    })

            if not formatted_transactions:
                return {'success': False, 'error': 'No valid transactions'}

            payload = {
                "currency": "KES",
                "provider": "MPESA-B2C",
                "transactions": formatted_transactions
            }

            logger.info(f"Sending bulk M-Pesa B2C: {len(formatted_transactions)} transactions")

            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=120
            )

            data = response.json()

            if response.status_code in [200, 201]:
                tracking_id = data.get('tracking_id')

                # Auto-approve if needed
                if data.get('status') == 'Preview and approve' and tracking_id:
                    return self._approve_transaction(tracking_id, f"BULK-{tracking_id}")

                return {
                    'success': True,
                    'tracking_id': tracking_id,
                    'status': data.get('status'),
                    'total_count': len(formatted_transactions),
                    'message': 'Bulk payment initiated'
                }
            else:
                error_msg = data.get('message') or data.get('error') or 'Bulk payment failed'
                return {
                    'success': False,
                    'error': error_msg,
                    'details': data
                }

        except requests.Timeout:
            logger.error("IntaSend bulk B2C timeout")
            return {'success': False, 'error': 'Request timeout'}
        except requests.RequestException as e:
            logger.exception("IntaSend bulk B2C request failed")
            return {'success': False, 'error': str(e)}

    def get_transaction_status(self, tracking_id: str) -> Dict:
        """
        Get status of a transaction.

        Args:
            tracking_id: IntaSend tracking ID

        Returns:
            Dict with transaction status
        """
        try:
            url = f"{self.base_url}/send-money/status/"

            payload = {
                "tracking_id": tracking_id
            }

            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )

            data = response.json()

            if response.status_code == 200:
                # Map IntaSend status to internal status
                status = data.get('status', 'PENDING')

                return {
                    'success': True,
                    'tracking_id': tracking_id,
                    'status': status,
                    'payment_status': self.map_status(status),
                    'transactions': data.get('transactions', [])
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message') or 'Status query failed'
                }

        except requests.RequestException as e:
            logger.exception(f"IntaSend status query failed for {tracking_id}")
            return {'success': False, 'error': str(e)}

    def get_wallet_balance(self) -> Dict:
        """Get wallet balance."""
        try:
            url = f"{self.base_url}/wallets/"

            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=30
            )

            data = response.json()

            if response.status_code == 200:
                return {
                    'success': True,
                    'wallets': data
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message') or 'Balance query failed'
                }

        except requests.RequestException as e:
            logger.exception("IntaSend balance query failed")
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
    def map_status(intasend_status: str) -> str:
        """
        Map IntaSend status to internal status.

        IntaSend statuses: Pending, Processed, Failed, etc.
        Internal statuses: paid, processing, failed, pending
        """
        status_map = {
            'Pending': 'processing',
            'Processing': 'processing',
            'Processed': 'paid',
            'Complete': 'paid',
            'Completed': 'paid',
            'Successful': 'paid',
            'Failed': 'failed',
            'Cancelled': 'failed',
            'Rejected': 'failed',
        }
        return status_map.get(intasend_status, 'processing')
