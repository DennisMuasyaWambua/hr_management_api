"""
IntaSend M-Pesa B2C Integration Service.

Handles M-Pesa Business to Customer (B2C) disbursements for payroll.
Uses the official IntaSend Python SDK for reliable payment processing.

To set up:
1. Register at https://intasend.com/
2. Get your API keys from the dashboard
3. For production: Complete KYC verification

Environment variables required:
- INTASEND_PUBLISHABLE_KEY: Your IntaSend publishable key
- INTASEND_SECRET_KEY: Your IntaSend secret key (token)
- INTASEND_SANDBOX: True for sandbox, False for production

Documentation: https://developers.intasend.com/docs/m-pesa-b2c
"""

import logging
from typing import Dict, List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# Try to import the official SDK
try:
    from intasend import APIService
    INTASEND_SDK_AVAILABLE = True
except ImportError:
    INTASEND_SDK_AVAILABLE = False
    logger.warning("intasend-python package not installed. Run: pip install intasend-python")


class IntaSendService:
    """
    IntaSend payment service for M-Pesa B2C disbursements.

    Uses the official IntaSend Python SDK for payment processing.
    Documentation: https://developers.intasend.com/
    """

    def __init__(
        self,
        publishable_key: str = None,
        secret_key: str = None,
        sandbox: bool = None
    ):
        """Initialize IntaSend service with credentials."""
        self.sandbox = sandbox if sandbox is not None else getattr(settings, 'INTASEND_SANDBOX', True)
        self.publishable_key = publishable_key or getattr(settings, 'INTASEND_PUBLISHABLE_KEY', '')
        self.secret_key = secret_key or getattr(settings, 'INTASEND_SECRET_KEY', '')

        # Initialize the SDK service if available
        self._service = None
        if INTASEND_SDK_AVAILABLE and self.secret_key and self.publishable_key:
            try:
                self._service = APIService(
                    token=self.secret_key,
                    publishable_key=self.publishable_key,
                    test=self.sandbox
                )
                logger.info(f"IntaSend SDK initialized (sandbox={self.sandbox})")
            except Exception as e:
                logger.error(f"Failed to initialize IntaSend SDK: {e}")

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

            if not self._service:
                if not INTASEND_SDK_AVAILABLE:
                    return {'success': False, 'error': 'IntaSend SDK not installed. Run: pip install intasend-python'}
                return {'success': False, 'error': 'IntaSend credentials not configured'}

            # Prepare transaction
            transactions = [
                {
                    'name': name,
                    'account': phone,
                    'amount': float(amount),
                    'narrative': narrative
                }
            ]

            logger.info(f"Sending M-Pesa B2C to {phone}: KES {amount} (ref: {reference})")

            # Send with auto-approval (requires_approval='NO')
            response = self._service.transfer.mpesa(
                currency='KES',
                transactions=transactions,
                requires_approval='NO'
            )

            tracking_id = response.get('tracking_id')
            status = response.get('status')
            status_code = response.get('status_code')

            logger.info(f"IntaSend response: status={status}, code={status_code}, tracking_id={tracking_id}")

            # Check if transaction was accepted
            if tracking_id:
                # Get transaction details
                txn_list = response.get('transactions', [])
                txn_status = txn_list[0].get('status') if txn_list else 'Pending'

                return {
                    'success': True,
                    'tracking_id': tracking_id,
                    'reference': reference,
                    'status': status,
                    'status_code': status_code,
                    'transaction_status': txn_status,
                    'message': 'Payment initiated successfully'
                }
            else:
                error_msg = response.get('message') or response.get('error') or 'Payment initiation failed'
                logger.error(f"IntaSend B2C failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'details': response
                }

        except Exception as e:
            logger.exception(f"IntaSend B2C request failed for {reference}")
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
            if not self._service:
                if not INTASEND_SDK_AVAILABLE:
                    return {'success': False, 'error': 'IntaSend SDK not installed. Run: pip install intasend-python'}
                return {'success': False, 'error': 'IntaSend credentials not configured'}

            # Format transactions for IntaSend SDK
            formatted_transactions = []
            for txn in transactions:
                phone = self._normalize_phone(txn.get('phone', ''))
                if phone:
                    formatted_transactions.append({
                        'name': txn.get('name', 'Employee'),
                        'account': phone,
                        'amount': float(txn.get('amount', 0)),
                        'narrative': narrative
                    })

            if not formatted_transactions:
                return {'success': False, 'error': 'No valid transactions'}

            logger.info(f"Sending bulk M-Pesa B2C: {len(formatted_transactions)} transactions")

            # Send with auto-approval
            response = self._service.transfer.mpesa(
                currency='KES',
                transactions=formatted_transactions,
                requires_approval='NO'
            )

            tracking_id = response.get('tracking_id')
            status = response.get('status')

            if tracking_id:
                return {
                    'success': True,
                    'tracking_id': tracking_id,
                    'status': status,
                    'total_count': len(formatted_transactions),
                    'message': 'Bulk payment initiated'
                }
            else:
                error_msg = response.get('message') or response.get('error') or 'Bulk payment failed'
                return {
                    'success': False,
                    'error': error_msg,
                    'details': response
                }

        except Exception as e:
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
            if not self._service:
                return {'success': False, 'error': 'IntaSend not configured'}

            response = self._service.transfer.status(tracking_id)

            status = response.get('status', 'PENDING')
            status_code = response.get('status_code', '')

            # Get individual transaction statuses
            transactions = response.get('transactions', [])

            return {
                'success': True,
                'tracking_id': tracking_id,
                'status': status,
                'status_code': status_code,
                'payment_status': self.map_status(status),
                'transactions': transactions,
                'wallet': response.get('wallet'),
                'paid_amount': response.get('paid_amount'),
                'failed_amount': response.get('failed_amount'),
                'actual_charges': response.get('actual_charges')
            }

        except Exception as e:
            logger.exception(f"IntaSend status query failed for {tracking_id}")
            return {'success': False, 'error': str(e)}

    def get_wallet_balance(self) -> Dict:
        """Get wallet balance."""
        try:
            if not self._service:
                return {'success': False, 'error': 'IntaSend not configured'}

            # The SDK doesn't have a direct wallet balance method,
            # so we use a status check which returns wallet info
            # Or we can make a direct API call
            import requests

            base_url = 'https://sandbox.intasend.com/api/v1' if self.sandbox else 'https://payment.intasend.com/api/v1'
            url = f'{base_url}/wallets/'
            headers = {
                'Authorization': f'Bearer {self.secret_key}',
                'Content-Type': 'application/json'
            }

            response = requests.get(url, headers=headers, timeout=30)
            data = response.json()

            if response.status_code == 200:
                # Find KES wallet
                wallets = data.get('results', [])
                kes_wallet = next((w for w in wallets if w.get('currency') == 'KES'), None)

                return {
                    'success': True,
                    'wallets': wallets,
                    'kes_balance': kes_wallet.get('available_balance') if kes_wallet else 0,
                    'kes_wallet': kes_wallet
                }
            else:
                return {
                    'success': False,
                    'error': data.get('message') or 'Balance query failed'
                }

        except Exception as e:
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

        IntaSend statuses: Pending, Processing payment, Completed, Failed, etc.
        Internal statuses: paid, processing, failed, pending
        """
        status_lower = intasend_status.lower() if intasend_status else ''

        if 'completed' in status_lower or 'successful' in status_lower:
            return 'paid'
        elif 'failed' in status_lower or 'cancelled' in status_lower or 'rejected' in status_lower:
            return 'failed'
        elif 'processing' in status_lower or 'confirming' in status_lower:
            return 'processing'
        else:
            return 'processing'  # Default to processing for pending/unknown states
