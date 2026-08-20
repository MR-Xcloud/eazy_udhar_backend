"""Push the money collected against an EazyUdhar invoice into CRM finance.

Companion to `crm_invoice_sync`, and split the same way CRM itself splits them:
the invoice push books the *sale*, this books the *receipt*. INWIZY is one
company, so an EazyUdhar collection belongs in the same finance ledger as
everything else — without this a paid subscription showed up in CRM only as an
invoice whose amount_paid happened to equal its total, with nothing under
Finance > Payments and no receipt document, so there was no record of how or
when the money actually arrived.

CRM's ingest allocates the payment against the invoice and mints its own
Payment and Receipt numbers, so the result is indistinguishable from one keyed
in through the finance UI. Idempotent on our invoice number, so a retry credits
the customer once.
"""

import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15

# Ours -> the modes CRM's finance module accepts. Razorpay collections are a
# gateway settlement; an offline payment is whatever the admin keyed in, which
# we cannot narrow further than "other" without a mode field of our own.
MODE_MAP = {
    'razorpay': 'gateway',
    'offline': 'other',
}


def _gateway_fee_rupees(invoice) -> float:
    """What Razorpay kept out of this collection, in rupees.

    Razorpay reports the real deduction on the payment entity: `fee` is the
    commission *including* the GST on it (`tax` is that GST alone), so `fee` is
    the whole amount that never reached the bank. Reading it beats estimating a
    percentage — the rate varies by instrument, and an estimate would put a
    wrong number in the finance ledger.

    Best effort: a fee we cannot look up is reported as zero rather than
    failing the receipt. Booking the collection matters more than the fee on
    it, and the gross is right either way.
    """
    if invoice.payment_method != 'razorpay':
        return 0.0

    payment_id = (invoice.offline_reference or '').strip()
    if not payment_id.startswith('pay_'):
        return 0.0

    try:
        from customerapp.razorpay_service import fetch_razorpay_payment

        data = fetch_razorpay_payment(payment_id) or {}
        return round(int(data.get('fee') or 0) / 100, 2)
    except Exception as exc:  # noqa: BLE001 — never fail a receipt over a fee
        logger.warning(
            'Could not read Razorpay fee for %s (%s): %s',
            invoice.invoice_number, payment_id, exc,
        )
        return 0.0


def build_payload(invoice) -> dict:
    total = round(float(invoice.amount) + float(invoice.tax_amount or 0), 2)
    paid_at = invoice.paid_at or invoice.created_at

    return {
        'source': 'eazyudhar',
        # Must match what crm_invoice_sync sent as `reference_no`.
        'invoice_reference_no': invoice.invoice_number,
        # One full-settlement receipt per invoice — EazyUdhar has no partial
        # collection — so the invoice number is also the idempotency key.
        'receipt_reference': invoice.invoice_number,
        'payment_date': timezone.localtime(paid_at).date().isoformat(),
        'amount': total,
        # Gross above; this is the slice the gateway kept, so CRM can show
        # net banked against it rather than assuming nothing was deducted.
        'transaction_charge': _gateway_fee_rupees(invoice),
        'payment_mode': MODE_MAP.get(invoice.payment_method, 'other'),
        'reference_no': invoice.offline_reference or None,
        'notes': f'EazyUdhar — payment for {invoice.invoice_number}',
    }


def push(invoice) -> bool:
    """Send the receipt for `invoice` to CRM finance. Returns True on success.

    Never raises — a CRM outage must not fail the request that took the money;
    `sync_crm_invoices` retries anything left unsynced.
    """
    url = (getattr(settings, 'CRM_API_URL', '') or '').rstrip('/')
    token = getattr(settings, 'CRM_API_TOKEN', '') or ''

    if not url or not token:
        logger.warning(
            'CRM receipt sync skipped — CRM_API_URL/CRM_API_TOKEN not configured (%s)',
            invoice.invoice_number,
        )
        return False

    if invoice.status != invoice.STATUS_PAID:
        logger.info(
            'CRM receipt sync skipped — %s is %s, not paid',
            invoice.invoice_number, invoice.status,
        )
        return False

    # Nothing to allocate against until the invoice itself has been ingested.
    # The callers push the invoice first on every path, so this only trips when
    # that push failed — and then it is the invoice retry that has to run first.
    if invoice.crm_sync_status != invoice.CRM_SYNC_SYNCED:
        logger.info(
            'CRM receipt sync skipped — invoice %s not synced yet (%s)',
            invoice.invoice_number, invoice.crm_sync_status,
        )
        return False

    try:
        response = requests.post(
            f'{url}/api/internal/payments',
            json=build_payload(invoice),
            headers={'X-Internal-Token': token},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.error('CRM receipt sync threw for %s: %s', invoice.invoice_number, exc)
        _mark(invoice, status='failed')
        return False

    if response.status_code not in (200, 201):
        logger.error(
            'CRM receipt sync failed for %s: HTTP %s %s',
            invoice.invoice_number, response.status_code, response.text[:500],
        )
        _mark(invoice, status='failed')
        return False

    try:
        body = response.json()
    except ValueError:
        logger.error(
            'CRM receipt sync got non-JSON for %s: %s',
            invoice.invoice_number, response.text[:500],
        )
        _mark(invoice, status='failed')
        return False

    _mark(
        invoice,
        status='synced',
        crm_receipt_no=body.get('receipt_no') or '',
        crm_receipt_id=body.get('receipt_id'),
    )

    logger.info(
        'CRM receipt sync ok: %s -> %s (%s)',
        invoice.invoice_number, body.get('receipt_no'), body.get('status'),
    )
    return True


def _mark(invoice, status: str, crm_receipt_no: str = '', crm_receipt_id=None) -> None:
    invoice.crm_receipt_sync_status = status
    invoice.crm_receipt_synced_at = timezone.now()
    fields = ['crm_receipt_sync_status', 'crm_receipt_synced_at']
    if crm_receipt_no:
        invoice.crm_receipt_no = crm_receipt_no
        fields.append('crm_receipt_no')
    if crm_receipt_id is not None:
        invoice.crm_receipt_id = crm_receipt_id
        fields.append('crm_receipt_id')
    invoice.save(update_fields=fields)
