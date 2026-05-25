from celery import shared_task
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import logging

from .models import PaymentBatch, PayrollRecord, PayrollRun
from .services.pesapal import PesaPalService

logger = logging.getLogger(__name__)


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

    # Initialize PesaPal with credentials from environment variables
    pesapal = PesaPalService()

    if not pesapal.consumer_key or not pesapal.consumer_secret:
        batch.status = 'failed'
        batch.save()
        logger.error("PesaPal credentials not configured in environment variables")
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
                # Payment initiated - mark as processing until IPN confirms
                record.payment_status = 'processing'
                record.payment_reference = result.get('order_tracking_id') or result.get('reference')
                successful += 1
                successful_amount += record.net_salary
            else:
                record.payment_status = 'failed'
                failed += 1
                failed_amount += record.net_salary

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
