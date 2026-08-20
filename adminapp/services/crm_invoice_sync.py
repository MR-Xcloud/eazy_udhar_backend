"""Push a paid subscription invoice into the CRM finance module.

Deliberately over HTTP rather than writing to the CRM database: CRM owns its
invoice numbering (row-locked, per financial year) and its ledger postings, and
inserting rows behind its back would desync both. The ingest endpoint is
idempotent on `source:reference_no`, so a retry never burns a second number.

Only `paid` invoices are pushed — a draft is not yet a booked sale, and the CRM
ledger should not carry a receivable EazyUdhar has not raised.
"""

import logging

import requests
from django.conf import settings
from django.utils import timezone

from .gst import SUPPLIER_STATE_CODE, state_code_from_gstin, state_name
from .invoice_pdf import invoice_pdf_path, write_invoice_pdf

logger = logging.getLogger(__name__)

# SAC for "IT / software support services" — same code the matrimonial SaaS
# pushes, so the CRM GST reports group INWIZY's SaaS revenue on one line.
SAC_CODE = '997331'

TIMEOUT_SECONDS = 15


def _gst_rate(invoice) -> float:
    """Effective GST percent, derived rather than stored: the invoice keeps
    amount + tax_amount only, and CRM computes its own line tax from a percent."""
    if not invoice.amount or not invoice.tax_amount:
        return 0.0
    return round(float(invoice.tax_amount) / float(invoice.amount) * 100, 2)


def build_payload(invoice) -> dict:
    seller = invoice.seller
    intra = invoice.tax_type == invoice.TAX_TYPE_CGST_SGST
    amount = float(invoice.amount)
    tax = float(invoice.tax_amount or 0)
    total = round(amount + tax, 2)

    # Place of supply: the seller's GSTIN state code when they gave us one,
    # otherwise the supplier's own state — the same fallback determine_tax_type()
    # used when it decided intra vs inter-state, so the two never disagree.
    code = state_code_from_gstin(seller.gst_number) or SUPPLIER_STATE_CODE

    invoiced_on = invoice.paid_at or invoice.created_at

    return {
        'source': 'eazyudhar',
        'reference_no': invoice.invoice_number,
        'invoice_date': timezone.localtime(invoiced_on).date().isoformat(),
        'customer_name': seller.business_name,
        'company_name': seller.business_name,
        'email': seller.email or None,
        'phone': seller.phone or None,
        'gstin': seller.gst_number or None,
        'pan': None,
        'place_of_supply_state': state_name(code),
        'place_of_supply_code': code,
        'gst_treatment': 'intra_state' if intra else 'inter_state',
        'taxable_amount': round(amount, 2),
        'cgst_amount': round(tax / 2, 2) if intra else 0,
        'sgst_amount': round(tax / 2, 2) if intra else 0,
        'igst_amount': 0 if intra else round(tax, 2),
        'grand_total': total,
        # Raised open, not pre-settled. The companion receipt push (see
        # `crm_receipt_sync`) books the money and flips it to paid, which is
        # what puts a Payment and a Receipt in CRM's finance module. Claiming
        # `paid` here instead would leave CRM nothing to allocate against — its
        # ingest caps allocation at the amount still due — so the money would
        # never appear under Payments at all.
        'amount_paid': 0,
        'status': 'sent',
        'notes': f'EazyUdhar — {invoice.line_description} ({invoice.invoice_number})',
        'items': [{
            'item_name': f'EazyUdhar — {invoice.line_description}',
            'description': (
                f'{timezone.localtime(invoice.period_start):%d %b %Y}'
                f' – {timezone.localtime(invoice.period_end):%d %b %Y}'
            ),
            'hsn_sac_code': SAC_CODE,
            'qty': 1,
            'rate': round(amount, 2),
            'tax_percent': _gst_rate(invoice),
        }],
    }


def push(invoice) -> bool:
    """Send `invoice` to CRM finance. Returns True on success. Never raises —
    a CRM outage must not fail the admin action that recorded the payment; the
    `sync_crm_invoices` command retries anything left unsynced."""
    url = (getattr(settings, 'CRM_API_URL', '') or '').rstrip('/')
    token = getattr(settings, 'CRM_API_TOKEN', '') or ''

    if not url or not token:
        logger.warning(
            'CRM invoice sync skipped — CRM_API_URL/CRM_API_TOKEN not configured (%s)',
            invoice.invoice_number,
        )
        return False

    if invoice.status != invoice.STATUS_PAID:
        logger.info(
            'CRM invoice sync skipped — %s is %s, not paid',
            invoice.invoice_number, invoice.status,
        )
        return False

    try:
        response = requests.post(
            f'{url}/api/internal/invoices',
            json=build_payload(invoice),
            headers={'X-Internal-Token': token},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.error('CRM invoice sync threw for %s: %s', invoice.invoice_number, exc)
        _mark(invoice, status='failed')
        return False

    if response.status_code not in (200, 201):
        logger.error(
            'CRM invoice sync failed for %s: HTTP %s %s',
            invoice.invoice_number, response.status_code, response.text[:500],
        )
        _mark(invoice, status='failed')
        return False

    try:
        body = response.json()
    except ValueError:
        logger.error(
            'CRM invoice sync got non-JSON for %s: %s',
            invoice.invoice_number, response.text[:500],
        )
        _mark(invoice, status='failed')
        return False

    was = invoice.crm_invoice_no
    _mark(
        invoice,
        status='synced',
        crm_invoice_no=body.get('invoice_no') or '',
        crm_invoice_id=body.get('invoice_id'),
    )

    # A PDF written before the number came back is the local rendering with the
    # local number. Replace it with CRM's own document now that there is one.
    if invoice.crm_invoice_no != was and invoice_pdf_path(invoice).exists():
        try:
            write_invoice_pdf(invoice)
        except Exception as exc:  # noqa: BLE001 — a stale PDF must not fail the sync
            logger.error('Invoice PDF re-render failed for %s: %s', invoice.invoice_number, exc)

    logger.info(
        'CRM invoice sync ok: %s → %s (%s)',
        invoice.invoice_number, body.get('invoice_no'), body.get('status'),
    )
    return True


def _mark(invoice, status: str, crm_invoice_no: str = '', crm_invoice_id=None) -> None:
    invoice.crm_sync_status = status
    invoice.crm_synced_at = timezone.now()
    fields = ['crm_sync_status', 'crm_synced_at']
    if crm_invoice_no:
        invoice.crm_invoice_no = crm_invoice_no
        fields.append('crm_invoice_no')
    if crm_invoice_id is not None:
        invoice.crm_invoice_id = crm_invoice_id
        fields.append('crm_invoice_id')
    invoice.save(update_fields=fields)
