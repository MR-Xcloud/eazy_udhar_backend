"""Invoices for add-on purchases — Excel-report access and prepaid SMS packs.

An add-on checkout is a one-off sale, not a billing cycle, so it has no
subscription to hang off: an Excel-report invoice records the access window the
purchase bought, an SMS pack invoice is dated to the day it was sold. Both then
go through the same machinery as subscription invoices — local numbering, PDF,
email, the CRM finance push — so all three land in one book on either side.
"""

import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from ..models import SubscriptionInvoice
from .crm_invoice_sync import push as push_invoice_to_crm
from .crm_receipt_sync import push as push_receipt_to_crm
from .gst import determine_tax_type
from .invoice_email import email_invoice
from .invoice_numbering import next_invoice_number
from .invoice_pdf import ensure_invoice_pdf

logger = logging.getLogger(__name__)

DEFAULT_GST_PERCENT = Decimal('18')


def _money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def split_gst_inclusive(total, gst_percent=DEFAULT_GST_PERCENT):
    """Add-on orders store the GST-inclusive amount charged to the seller; an
    invoice needs it back as taxable value + tax. Derived from the stored total
    rather than recomputed from the plan price, so the invoice always reconciles
    with what Razorpay actually took even if the plan was repriced since."""
    total = _money(total)
    rate = Decimal(str(gst_percent))
    taxable = _money(total / (Decimal('1') + rate / Decimal('100')))
    return taxable, _money(total - taxable)


def _describe(order):
    """(kind, plan_name, link_field, access_days) for either add-on order type."""
    if hasattr(order, 'plan_slug'):  # SellerExcelReportOrder
        return (
            SubscriptionInvoice.KIND_ADDON_EXCEL,
            order.plan_name,
            'addon_order',
            order.duration_days,
        )
    # SellerSmsPackOrder — a consumable top-up, so no access window.
    return (
        SubscriptionInvoice.KIND_ADDON_SMS,
        order.pack_name,
        'sms_pack_order',
        0,
    )


@transaction.atomic
def invoice_for_addon_order(order, *, gst_percent=DEFAULT_GST_PERCENT):
    """Raise (or return) the invoice for a paid add-on order. Idempotent — an
    order already invoiced returns its existing invoice, so a retried payment
    verification never mints a second number."""
    kind, plan_name, link_field, access_days = _describe(order)

    existing = SubscriptionInvoice.objects.filter(**{link_field: order}).first()
    if existing is not None:
        return existing

    if order.status != order.STATUS_PAID:
        raise ValueError(f'Add-on order {order.reference_id} is not paid.')

    taxable, tax = split_gst_inclusive(order.amount, gst_percent)
    paid_at = order.paid_at or timezone.now()

    return SubscriptionInvoice.objects.create(
        kind=kind,
        subscription=None,
        seller=order.seller,
        plan_name=plan_name,
        invoice_number=next_invoice_number(),
        amount=taxable,
        tax_amount=tax,
        tax_type=determine_tax_type(order.seller.gst_number),
        status=SubscriptionInvoice.STATUS_PAID,
        payment_method=SubscriptionInvoice.PAYMENT_METHOD_RAZORPAY,
        offline_reference=order.razorpay_payment_id or '',
        notes=f'{plan_name} — {order.reference_id}',
        paid_at=paid_at,
        period_start=paid_at,
        period_end=paid_at + timedelta(days=access_days),
        **{link_field: order},
    )


def issue_addon_invoice(order, *, gst_percent=DEFAULT_GST_PERCENT, email=True):
    """Invoice a paid add-on order: book it into CRM finance, render the PDF and
    email it to the seller — all inline, so the buyer has their GST invoice by
    the time the app confirms the purchase.

    Never raises: by the time this runs the seller has already paid and had the
    add-on credited, so a billing hiccup must not fail that request. The
    `sync_crm_invoices` command picks up anything that did not reach CRM, and
    the panel's Email button re-sends anything that did not go out.
    """
    try:
        invoice = invoice_for_addon_order(order, gst_percent=gst_percent)
    except Exception as exc:  # noqa: BLE001
        logger.error('Add-on invoice creation failed for %s: %s', order.reference_id, exc)
        return None

    try:
        # CRM mints the number the PDF and the email have to carry, so push
        # first, then render, then send.
        push_invoice_to_crm(invoice)
        # The order is already paid, so book the receipt straight away — that
        # is what settles the CRM invoice and files the payment.
        push_receipt_to_crm(invoice)
        ensure_invoice_pdf(invoice)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            'Add-on invoice finalisation failed for %s: %s', invoice.invoice_number, exc
        )

    if email and not invoice.emailed_at:
        try:
            result = email_invoice(invoice)
            if not result.get('sent'):
                logger.error(
                    'Add-on invoice email failed for %s: %s',
                    invoice.invoice_number, result.get('error'),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                'Add-on invoice email threw for %s: %s', invoice.invoice_number, exc
            )

    return invoice
