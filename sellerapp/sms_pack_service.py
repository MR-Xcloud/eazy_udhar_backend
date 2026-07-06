"""Prepaid SMS pack catalog checkout via Razorpay."""

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from adminapp.models import RazorpayPayment, SmsPack
from adminapp.services.sms_packs import sms_pack_pricing, sms_pack_to_dict
from customerapp.razorpay_service import (
    RazorpayError,
    _amount_paise,
    _razorpay_request,
    razorpay_configured,
    verify_payment_signature,
)
from easyudhar.razorpay_config import get_razorpay_credentials

from .models import SellerSettings, SellerSmsPackOrder


def get_sms_pack_balance(seller):
    settings, _ = SellerSettings.objects.get_or_create(seller=seller)
    return int(settings.sms_pack_balance or 0)


@transaction.atomic
def credit_sms_pack_balance(seller, quantity):
    qty = int(quantity)
    if qty <= 0:
        return get_sms_pack_balance(seller)
    settings, _ = SellerSettings.objects.select_for_update().get_or_create(
        seller=seller
    )
    settings.sms_pack_balance = int(settings.sms_pack_balance or 0) + qty
    settings.save(update_fields=['sms_pack_balance', 'updated_at'])
    return settings.sms_pack_balance


@transaction.atomic
def consume_sms_pack_credit(seller, count=1):
    """Use prepaid SMS credits when plan quota for the period is exhausted."""
    count = int(count)
    if count <= 0:
        return
    settings, _ = SellerSettings.objects.select_for_update().get_or_create(
        seller=seller
    )
    balance = int(settings.sms_pack_balance or 0)
    if balance <= 0:
        return
    settings.sms_pack_balance = max(0, balance - count)
    settings.save(update_fields=['sms_pack_balance', 'updated_at'])


def list_active_sms_packs():
    packs = SmsPack.objects.filter(is_active=True).order_by('sort_order', 'sms_quantity')
    return [sms_pack_to_dict(p) for p in packs]


@transaction.atomic
def create_sms_pack_order(*, seller, pack_slug):
    if not razorpay_configured():
        raise RazorpayError(
            'Razorpay is not configured.',
            code='razorpay_not_configured',
        )

    slug = (pack_slug or '').strip()
    pack = SmsPack.objects.filter(slug=slug, is_active=True).first()
    if pack is None:
        raise RazorpayError('SMS pack not found.', code='invalid_pack')

    pricing = sms_pack_pricing(pack)
    amount = Decimal(str(pricing['total_inr']))
    if amount <= 0:
        raise RazorpayError('This SMS pack is not available.', code='invalid_pack')

    reference_id = f'SMS-{uuid.uuid4().hex[:12].upper()}'
    amount_paise = _amount_paise(amount)

    order_payload = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': reference_id,
        'notes': {
            'type': 'seller_sms_pack',
            'seller_id': str(seller.id),
            'pack_slug': pack.slug,
            'sms_quantity': str(pack.sms_quantity),
        },
    }
    rz_order = _razorpay_request('POST', '/orders', order_payload)

    SellerSmsPackOrder.objects.create(
        seller=seller,
        pack_slug=pack.slug,
        pack_name=pack.name,
        sms_quantity=pack.sms_quantity,
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
        'pack_slug': pack.slug,
        'pack_name': pack.name,
        'sms_quantity': int(pack.sms_quantity),
        'amount_display': float(amount),
        'subtotal_inr': pricing['subtotal_inr'],
        'gst_amount_inr': pricing['gst_amount_inr'],
        'total_inr': pricing['total_inr'],
        'price_note': pricing['price_note'],
    }


@transaction.atomic
def verify_sms_pack_payment(
    *,
    seller,
    pack_slug,
    razorpay_order_id,
    razorpay_payment_id,
    razorpay_signature,
):
    order = (
        SellerSmsPackOrder.objects.select_for_update()
        .filter(
            seller=seller,
            razorpay_order_id=razorpay_order_id,
            pack_slug=pack_slug,
        )
        .first()
    )
    if order is None:
        raise RazorpayError('SMS pack order not found.', code='order_not_found')

    if order.status == SellerSmsPackOrder.STATUS_PAID:
        from .subscription_service import subscription_status_payload

        return {
            'message': 'SMS pack already credited',
            'sms_pack_balance': get_sms_pack_balance(seller),
            'subscription': subscription_status_payload(seller),
            'pack_slug': order.pack_slug,
            'sms_quantity': order.sms_quantity,
        }

    if not verify_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    ):
        order.status = SellerSmsPackOrder.STATUS_FAILED
        order.error_message = 'Invalid payment signature'
        order.save(update_fields=['status', 'error_message'])
        raise RazorpayError('Payment verification failed.', code='invalid_signature')

    now = timezone.now()
    order.status = SellerSmsPackOrder.STATUS_PAID
    order.razorpay_payment_id = razorpay_payment_id
    order.paid_at = now
    order.save(
        update_fields=['status', 'razorpay_payment_id', 'paid_at'],
    )

    RazorpayPayment.objects.create(
        seller=seller,
        order_id=razorpay_order_id,
        payment_id=razorpay_payment_id,
        amount=order.amount,
        currency='INR',
        status='captured',
        method='sms_pack',
    )

    new_balance = credit_sms_pack_balance(seller, order.sms_quantity)

    from .subscription_service import subscription_status_payload

    return {
        'message': 'SMS pack purchased',
        'sms_pack_balance': new_balance,
        'sms_quantity_added': order.sms_quantity,
        'subscription': subscription_status_payload(seller),
        'pack_slug': order.pack_slug,
        'pack_name': order.pack_name,
    }
