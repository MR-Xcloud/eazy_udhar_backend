"""On-demand Excel report addon — time-limited checkout via Razorpay.

Buying a plan grants access for its duration. Renewing before expiry extends
from the current expiry date rather than from now, so paid time is never lost.
"""

import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from adminapp.models import RazorpayPayment
from customerapp.razorpay_service import (
    RazorpayError,
    _amount_paise,
    _razorpay_request,
    razorpay_configured,
    verify_payment_signature,
)
from easyudhar.razorpay_config import get_razorpay_credentials

from .models import SellerExcelReportOrder, SellerSettings

EXCEL_REPORT_GST_PERCENT = Decimal('18')

EXCEL_REPORT_ADDON_PLANS = {
    '1m': {'name': '1 Month', 'duration_days': 30, 'price_inr': Decimal('49')},
    '3m': {'name': '3 Months', 'duration_days': 90, 'price_inr': Decimal('149')},
    '6m': {'name': '6 Months', 'duration_days': 180, 'price_inr': Decimal('299')},
    '12m': {'name': '12 Months', 'duration_days': 365, 'price_inr': Decimal('579')},
}


def _money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _with_gst(subtotal):
    """Addon prices are exclusive of GST; return subtotal / gst / total."""
    subtotal = _money(subtotal)
    gst_amount = _money(subtotal * EXCEL_REPORT_GST_PERCENT / Decimal('100'))
    total = _money(subtotal + gst_amount)
    return {
        'subtotal': subtotal,
        'gst_percent': float(EXCEL_REPORT_GST_PERCENT),
        'gst_amount': gst_amount,
        'total': total,
        'price_note': f'All prices are exclusive of {float(EXCEL_REPORT_GST_PERCENT):g}% GST',
    }


def list_excel_report_addon_plans():
    plans = []
    for slug, plan in EXCEL_REPORT_ADDON_PLANS.items():
        pricing = _with_gst(plan['price_inr'])
        plans.append(
            {
                'plan_slug': slug,
                'name': plan['name'],
                'duration_days': plan['duration_days'],
                'price_inr': float(pricing['subtotal']),
                'gst_percent': pricing['gst_percent'],
                'gst_amount_inr': float(pricing['gst_amount']),
                'total_inr': float(pricing['total']),
                'price_note': pricing['price_note'],
            }
        )
    return plans


def _addon_expiry(seller):
    settings_row, _ = SellerSettings.objects.get_or_create(seller=seller)
    return settings_row.excel_report_addon_expires_at


def has_excel_report_access(seller):
    expires_at = _addon_expiry(seller)
    return bool(expires_at and expires_at > timezone.now())


def excel_report_addon_status(seller):
    expires_at = _addon_expiry(seller)
    now = timezone.now()
    active = bool(expires_at and expires_at > now)
    return {
        'active': active,
        'expires_at': expires_at.isoformat() if expires_at else None,
        'days_remaining': max((expires_at - now).days, 0) if active else 0,
        'plans': list_excel_report_addon_plans(),
    }


@transaction.atomic
def extend_excel_report_addon(seller, duration_days):
    settings_row, _ = SellerSettings.objects.select_for_update().get_or_create(
        seller=seller
    )
    now = timezone.now()
    base = settings_row.excel_report_addon_expires_at
    start_from = base if base and base > now else now
    settings_row.excel_report_addon_expires_at = start_from + timedelta(days=duration_days)
    settings_row.save(update_fields=['excel_report_addon_expires_at'])
    return settings_row.excel_report_addon_expires_at


@transaction.atomic
def create_excel_report_addon_order(*, seller, plan_slug):
    if not razorpay_configured():
        raise RazorpayError(
            'Razorpay is not configured.',
            code='razorpay_not_configured',
        )

    slug = (plan_slug or '').strip()
    plan = EXCEL_REPORT_ADDON_PLANS.get(slug)
    if plan is None:
        raise RazorpayError('Excel report addon plan not found.', code='invalid_plan')

    pricing = _with_gst(plan['price_inr'])
    amount = pricing['total']  # charge base + 18% GST
    reference_id = f'XLR-{uuid.uuid4().hex[:12].upper()}'
    amount_paise = _amount_paise(amount)

    order_payload = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': reference_id,
        'notes': {
            'type': 'seller_excel_report_addon',
            'seller_id': str(seller.id),
            'plan_slug': slug,
            'duration_days': str(plan['duration_days']),
            'gst_percent': str(pricing['gst_percent']),
            'gst_amount_inr': str(pricing['gst_amount']),
            'subtotal_inr': str(pricing['subtotal']),
        },
    }
    rz_order = _razorpay_request('POST', '/orders', order_payload)

    SellerExcelReportOrder.objects.create(
        seller=seller,
        plan_slug=slug,
        plan_name=plan['name'],
        duration_days=plan['duration_days'],
        amount=amount,
        reference_id=reference_id,
        razorpay_order_id=rz_order['id'],
    )

    key_id, _, _ = get_razorpay_credentials()
    return {
        'order_id': rz_order['id'],
        'amount': amount_paise,
        'currency': 'INR',
        'key_id': key_id,
        'reference_id': reference_id,
        'plan_slug': slug,
        'plan_name': plan['name'],
        'duration_days': plan['duration_days'],
        'amount_display': float(amount),
        'subtotal_inr': float(pricing['subtotal']),
        'gst_percent': pricing['gst_percent'],
        'gst_amount_inr': float(pricing['gst_amount']),
        'total_inr': float(pricing['total']),
        'price_note': pricing['price_note'],
    }


@transaction.atomic
def verify_excel_report_addon_payment(
    *,
    seller,
    razorpay_order_id,
    razorpay_payment_id,
    razorpay_signature,
):
    order = (
        SellerExcelReportOrder.objects.select_for_update()
        .filter(seller=seller, razorpay_order_id=razorpay_order_id)
        .first()
    )
    if order is None:
        raise RazorpayError('Excel report addon order not found.', code='order_not_found')

    if order.status == SellerExcelReportOrder.STATUS_PAID:
        return {
            'message': 'Excel report addon already active',
            'addon': excel_report_addon_status(seller),
        }

    if not verify_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    ):
        order.status = SellerExcelReportOrder.STATUS_FAILED
        order.error_message = 'Invalid payment signature'
        order.save(update_fields=['status', 'error_message'])
        raise RazorpayError('Payment verification failed.', code='invalid_signature')

    now = timezone.now()
    order.status = SellerExcelReportOrder.STATUS_PAID
    order.razorpay_payment_id = razorpay_payment_id
    order.paid_at = now
    order.save(update_fields=['status', 'razorpay_payment_id', 'paid_at'])

    RazorpayPayment.objects.create(
        seller=seller,
        order_id=razorpay_order_id,
        payment_id=razorpay_payment_id,
        amount=order.amount,
        currency='INR',
        status='captured',
        method='excel_report_addon',
    )

    extend_excel_report_addon(seller, order.duration_days)

    return {
        'message': 'Excel report addon activated',
        'addon': excel_report_addon_status(seller),
    }
