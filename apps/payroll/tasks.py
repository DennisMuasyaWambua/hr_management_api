from celery import shared_task
from django.utils import timezone
from django.db import transaction, connection
from django.conf import settings
from decimal import Decimal
import logging
import uuid
import time

from .models import PaymentBatch, PayrollRecord, PayrollRun
from .services.pesapal import PesaPalService
from .services.daraja import DarajaService
from .services.intasend import IntaSendService
from .services.africastalking_sms import AfricasTalkingSMSService

logger = logging.getLogger(__name__)


def get_employee_full_name(user_id: str, fallback: str = "Valued Employee") -> str:
    """Fetch employee's full name from users table."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT full_name FROM users WHERE id = %s",
                [user_id]
            )
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
    except Exception as e:
        logger.warning(f"Could not fetch user name for {user_id}: {e}")
    return fallback


def send_demo_sms(phone: str, employee_name: str, amount: float, company_name: str):
    """Send SMS notification in demo mode using Africa's Talking."""
    sms_service = AfricasTalkingSMSService()

    message = (
        f"Dear {employee_name}, your salary of KES {amount:,.2f} "
        f"has been sent to your M-Pesa by {company_name}. "
        f"Thank you for your service."
    )

    if sms_service.api_key:
        try:
            result = sms_service.send_sms(phone, message)
            if result.get('success'):
                logger.info(f"SMS sent to {phone} via Africa's Talking")
            return result
        except Exception as e:
            logger.warning(f"SMS send failed: {e}")

    # If SMS fails, log but don't block
    logger.info(f"[DEMO] SMS notification for {phone}: {message}")
    return {'success': True, 'demo': True}


def _process_demo_payments(batch):
    """
    Process payments in demo mode - simulates successful payments and sends SMS notifications.
    Used for demonstrations when real payment APIs aren't available.
    """
    from .models import PayrollRecord

    records = PayrollRecord.objects.filter(
        payroll_run=batch.payroll_run,
        payment_method=batch.payment_method,
        payment_status='pending'
    ).select_related('employee')

    successful = 0
    successful_amount = Decimal('0')
    company_name = batch.payroll_run.company.name if batch.payroll_run.company else "Your Employer"

    for record in records:
        # Mark as processing
        record.payment_status = 'processing'
        record.save()

        # Simulate processing delay (makes demo more realistic)
        time.sleep(0.5)

        # Generate a demo reference
        demo_reference = f"DEMO-{uuid.uuid4().hex[:8].upper()}"

        # Get phone number
        phone = record.employee.mpesa_number or record.employee.airtel_number

        # Send SMS notification
        if phone:
            # Get actual employee name from users table
            employee_name = get_employee_full_name(
                str(record.employee.user_id),
                fallback=record.employee.job_title
            )
            send_demo_sms(
                phone=phone,
                employee_name=employee_name,
                amount=float(record.net_salary),
                company_name=company_name
            )

        # Mark as paid (simulated success)
        record.payment_status = 'paid'
        record.payment_reference = demo_reference
        record.paid_at = timezone.now()
        record.save()

        successful += 1
        successful_amount += record.net_salary

        logger.info(f"[DEMO] Payment processed for {record.employee.employee_number}: KES {record.net_salary}")

    # Update batch
    batch.successful_count = successful
    batch.failed_count = 0
    batch.successful_amount = successful_amount
    batch.failed_amount = Decimal('0')
    batch.status = 'completed'
    batch.completed_at = timezone.now()
    batch.save()

    # Update payroll run status
    batch.payroll_run.status = 'completed'
    batch.payroll_run.completed_at = timezone.now()
    batch.payroll_run.save()

    logger.info(f"[DEMO] Batch completed: {successful} payments, KES {successful_amount}")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_payment_batch(self, batch_id: str):
    """
    Process a payment batch asynchronously.
    Handles Bank, M-Pesa, and Airtel Money payments via PesaPal.
    """
    try:
        batch = PaymentBatch.objects.select_related('payroll_run__company').get(id=batch_id)
    except PaymentBatch.DoesNotExist:
        logger.error(f"Payment batch {batch_id} not found")
        return

    batch.status = 'processing'
    batch.started_at = timezone.now()
    batch.save()

    # Check if demo mode is enabled
    demo_mode = getattr(settings, 'PAYMENT_DEMO_MODE', False)

    if demo_mode:
        logger.info(f"[DEMO MODE] Processing payment batch {batch_id}")
        _process_demo_payments(batch)
        return

    # Initialize payment services
    pesapal = PesaPalService()
    daraja = DarajaService()
    intasend = IntaSendService()

    # Check which service to use for M-Pesa (priority: IntaSend > Daraja > PesaPal)
    use_intasend_for_mpesa = bool(intasend.secret_key)
    use_daraja_for_mpesa = not use_intasend_for_mpesa and daraja.consumer_key and daraja.consumer_secret

    if batch.payment_method == 'mpesa':
        if not use_intasend_for_mpesa and not use_daraja_for_mpesa:
            if not pesapal.consumer_key or not pesapal.consumer_secret:
                batch.status = 'failed'
                batch.save()
                logger.error("No M-Pesa payment provider configured (IntaSend, Daraja, or PesaPal)")
                return
    elif batch.payment_method != 'mpesa':
        if not pesapal.consumer_key or not pesapal.consumer_secret:
            batch.status = 'failed'
            batch.save()
            logger.error("PesaPal credentials not configured for bank/airtel payments")
            return

    # Get pending records for this batch
    records = PayrollRecord.objects.filter(
        payroll_run=batch.payroll_run,
        payment_method=batch.payment_method,
        payment_status='pending'
    ).select_related('employee')

    successful = 0
    failed = 0
    successful_amount = Decimal('0')
    failed_amount = Decimal('0')

    for record in records:
        record.payment_status = 'processing'
        record.save()

        try:
            # Build payment request based on method
            if batch.payment_method == 'mpesa':
                if not record.employee.mpesa_number:
                    raise ValueError("M-Pesa number not configured")

                # Use IntaSend > Daraja > PesaPal for M-Pesa B2C
                if use_intasend_for_mpesa:
                    result = intasend.send_mpesa(
                        phone=record.employee.mpesa_number,
                        amount=float(record.net_salary),
                        reference=f"SAL-{record.id}",
                        name=record.employee.job_title,
                        narrative="Salary Payment"
                    )
                    if result.get('success'):
                        result['reference'] = result.get('tracking_id')
                elif use_daraja_for_mpesa:
                    result = daraja.send_b2c(
                        phone=record.employee.mpesa_number,
                        amount=float(record.net_salary),
                        reference=f"SAL-{record.id}",
                        remarks="Salary Payment"
                    )
                    if result.get('success'):
                        result['reference'] = result.get('conversation_id') or result.get('originator_conversation_id')
                else:
                    result = pesapal.send_mpesa(
                        phone=record.employee.mpesa_number,
                        amount=float(record.net_salary),
                        reference=f"SAL-{record.id}"
                    )
            elif batch.payment_method == 'airtel':
                if not record.employee.airtel_number:
                    raise ValueError("Airtel number not configured")
                result = pesapal.send_airtel(
                    phone=record.employee.airtel_number,
                    amount=float(record.net_salary),
                    reference=f"SAL-{record.id}"
                )
            else:  # bank
                if not record.employee.bank_account:
                    raise ValueError("Bank account not configured")
                result = pesapal.send_bank_eft(
                    bank_name=record.employee.bank_name or '',
                    account_number=record.employee.bank_account,
                    amount=float(record.net_salary),
                    reference=f"SAL-{record.id}",
                    account_name=record.employee.job_title  # Using job_title as name placeholder
                )

            if result.get('success'):
                # Payment initiated - mark as processing until callback confirms
                record.payment_status = 'processing'
                record.payment_reference = result.get('order_tracking_id') or result.get('reference') or result.get('conversation_id')
                successful += 1
                successful_amount += record.net_salary

                # Send SMS notification via Africa's Talking
                try:
                    sms_service = AfricasTalkingSMSService()
                    if sms_service.api_key:
                        phone = record.employee.mpesa_number or record.employee.airtel_number
                        if phone:
                            company_name = batch.payroll_run.company.name if batch.payroll_run.company else "Your Employer"
                            # Get actual employee name from users table
                            employee_name = get_employee_full_name(
                                str(record.employee.user_id),
                                fallback=record.employee.job_title
                            )
                            sms_result = sms_service.send_payment_notification(
                                phone=phone,
                                employee_name=employee_name,
                                amount=float(record.net_salary),
                                company_name=company_name
                            )
                            if sms_result.get('success'):
                                logger.info(f"SMS notification sent to {phone}")
                            else:
                                logger.warning(f"SMS notification failed: {sms_result.get('error')}")
                except Exception as sms_error:
                    logger.warning(f"SMS notification error: {sms_error}")
            else:
                record.payment_status = 'failed'
                failed += 1
                failed_amount += record.net_salary
                logger.error(f"Payment failed for {record.id}: {result.get('error')}")

        except Exception as e:
            logger.exception(f"Payment failed for record {record.id}")
            record.payment_status = 'failed'
            failed += 1
            failed_amount += record.net_salary

        record.save()

    # Update batch summary
    batch.successful_count = successful
    batch.failed_count = failed
    batch.successful_amount = successful_amount
    batch.failed_amount = failed_amount
    batch.completed_at = timezone.now()

    if failed == 0 and successful > 0:
        batch.status = 'processing'  # Waiting for IPN confirmations
    elif successful == 0:
        batch.status = 'failed'
    else:
        batch.status = 'partial'

    batch.save()

    # Schedule status polling for processing payments
    if successful > 0:
        poll_payment_statuses.apply_async(
            args=[str(batch.payroll_run_id)],
            countdown=60  # Check after 1 minute
        )


@shared_task(bind=True, max_retries=10, default_retry_delay=120)
def poll_payment_statuses(self, payroll_run_id: str):
    """
    Poll PesaPal for payment statuses of processing payments.
    This is a fallback for when IPN doesn't arrive.
    """
    try:
        payroll_run = PayrollRun.objects.select_related('company').get(id=payroll_run_id)
    except PayrollRun.DoesNotExist:
        logger.error(f"Payroll run {payroll_run_id} not found")
        return

    # Initialize PesaPal with credentials from environment variables
    pesapal = PesaPalService()

    # Get payments still in processing state with a reference
    processing_records = PayrollRecord.objects.filter(
        payroll_run=payroll_run,
        payment_status='processing',
        payment_reference__isnull=False
    ).exclude(payment_reference='')

    still_processing = 0
    updated = 0

    for record in processing_records:
        try:
            status_result = pesapal.get_transaction_status(record.payment_reference)

            if status_result.get('success'):
                pesapal_status = status_result.get('payment_status', 'PENDING')
                new_status = PesaPalService.map_payment_status(pesapal_status)

                if new_status != 'processing':
                    record.payment_status = new_status
                    if new_status == 'paid':
                        record.paid_at = timezone.now()
                    elif new_status == 'failed':
                        record.payment_error = status_result.get('message', 'Payment failed')
                    record.save()
                    updated += 1
                else:
                    still_processing += 1
            else:
                still_processing += 1

        except Exception as e:
            logger.exception(f"Failed to poll status for record {record.id}")
            still_processing += 1

    logger.info(f"Polled {processing_records.count()} payments: {updated} updated, {still_processing} still processing")

    # If there are still processing payments, schedule another poll
    if still_processing > 0:
        # Retry with exponential backoff, max 10 retries
        raise self.retry(exc=Exception("Still processing payments"))

    # All done, check completion
    check_payroll_completion.delay(payroll_run_id)


@shared_task
def check_payroll_completion(payroll_run_id: str):
    """Check if all payments are complete and update payroll run status"""
    try:
        payroll_run = PayrollRun.objects.get(id=payroll_run_id)
    except PayrollRun.DoesNotExist:
        return

    pending = payroll_run.records.filter(payment_status__in=['pending', 'processing']).count()

    if pending == 0:
        paid = payroll_run.records.filter(payment_status='paid').count()
        failed = payroll_run.records.filter(payment_status='failed').count()

        if failed == 0 and paid > 0:
            payroll_run.status = 'completed'
        elif paid == 0:
            payroll_run.status = 'failed'
        else:
            payroll_run.status = 'completed'  # Partial success is still completed

        payroll_run.save()

        # Update all batches
        for batch in payroll_run.payment_batches.filter(status='processing'):
            batch_records = payroll_run.records.filter(payment_method=batch.payment_method)
            batch.successful_count = batch_records.filter(payment_status='paid').count()
            batch.failed_count = batch_records.filter(payment_status='failed').count()
            batch.successful_amount = sum(
                r.net_salary for r in batch_records.filter(payment_status='paid')
            )
            batch.failed_amount = sum(
                r.net_salary for r in batch_records.filter(payment_status='failed')
            )

            if batch.failed_count == 0:
                batch.status = 'completed'
            elif batch.successful_count == 0:
                batch.status = 'failed'
            else:
                batch.status = 'partial'

            batch.completed_at = timezone.now()
            batch.save()


@shared_task
def process_ipn_callback(order_tracking_id: str, payment_status: str, confirmation_code: str = None):
    """
    Process IPN callback from PesaPal.
    Called by the IPN webhook view.
    """
    try:
        # Find the payment record by reference
        record = PayrollRecord.objects.select_related('payroll_run').get(
            payment_reference=order_tracking_id
        )
    except PayrollRecord.DoesNotExist:
        logger.warning(f"Payment record not found for tracking ID: {order_tracking_id}")
        return
    except PayrollRecord.MultipleObjectsReturned:
        logger.error(f"Multiple records found for tracking ID: {order_tracking_id}")
        return

    # Map PesaPal status to internal status
    new_status = PesaPalService.map_payment_status(payment_status)

    if record.payment_status in ['paid', 'failed']:
        # Already finalized, skip
        logger.info(f"Payment {order_tracking_id} already finalized as {record.payment_status}")
        return

    with transaction.atomic():
        record.payment_status = new_status
        if new_status == 'paid':
            record.paid_at = timezone.now()
            if confirmation_code:
                record.payment_reference = f"{record.payment_reference}|{confirmation_code}"
        elif new_status == 'failed':
            record.payment_error = f"Payment {payment_status}"

        record.save()

    # Check if payroll is complete
    check_payroll_completion.delay(str(record.payroll_run_id))

    logger.info(f"IPN processed: {order_tracking_id} -> {new_status}")
