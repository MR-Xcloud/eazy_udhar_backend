"""Razorpay checkout for seller-initiated customer payments."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from easyudhar.payment_utils import razorpay_method_to_standard

from customerapp.razorpay_service import (
    RazorpayError,
    _amount_paise,
    _razorpay_request,
    razorpay_configured,
    resolve_razorpay_payment_method,
    verify_payment_signature,
)
from easyudhar.razorpay_config import get_razorpay_credentials

from .models import SellerCustomer, SellerRazorpayOrder
from .services import receive_payment


def _validate_amount(customer, amount):
    pay_amount = Decimal(str(amount))
    if pay_amount <= 0:
        raise RazorpayError('Amount must be greater than zero.', code='invalid_amount')
    outstanding = customer.outstanding_amount
    if pay_amount > outstanding:
        raise RazorpayError(
            f'Amount exceeds outstanding balance (max Rs.{outstanding}).',
            code='amount_exceeds_due',
        )
    return pay_amount


@transaction.atomic
def create_seller_razorpay_order(*, seller, customer, amount, note=''):
    if not razorpay_configured():
        raise RazorpayError(
            'Razorpay is not configured. Set RAZORPAY_TEST_KEY_ID and RAZORPAY_TEST_KEY_SECRET.',
            code='razorpay_not_configured',
        )

    pay_amount = _validate_amount(customer, amount)
    reference_id = f'SPAY-{uuid.uuid4().hex[:12].upper()}'

    from easyudhar.razorpay_route import (
        attach_transfers_to_order_payload,
        transfers_for_single_seller,
    )

    transfers, transfer_total = transfers_for_single_seller(seller, pay_amount)
    order_amount_paise = _amount_paise(pay_amount)
    if transfer_total != order_amount_paise:
        raise RazorpayError(
            'Payout split does not match payment amount.',
            code='transfer_mismatch',
        )

    order_payload = attach_transfers_to_order_payload(
        {
            'amount': order_amount_paise,
            'currency': 'INR',
            'receipt': reference_id,
            'notes': {
                'seller_id': str(seller.id),
                'customer_id': str(customer.id),
            },
        },
        transfers,
    )
    rz_order = _razorpay_request('POST', '/orders', order_payload)

    SellerRazorpayOrder.objects.create(
        seller=seller,
        customer=customer,
        amount=pay_amount,
        note=note or '',
        reference_id=reference_id,
        razorpay_order_id=rz_order['id'],
        status=SellerRazorpayOrder.STATUS_PENDING,
    )
    key_id, _, _ = get_razorpay_credentials()
    return {
        'order_id': rz_order['id'],
        'amount': _amount_paise(pay_amount),
        'currency': 'INR',
        'key_id': key_id,
        'reference_id': reference_id,
        'mode': settings.RAZORPAY_MODE,
        'max_payable': str(customer.outstanding_amount),
        'is_partial': pay_amount < customer.outstanding_amount,
        'partial_payment_allowed': True,
    }


@transaction.atomic
def verify_and_settle_seller_payment(
    *,
    seller,
    customer,
    razorpay_order_id,
    razorpay_payment_id,
    razorpay_signature,
):
    order = (
        SellerRazorpayOrder.objects.select_for_update()
        .filter(
            seller=seller,
            customer=customer,
            razorpay_order_id=razorpay_order_id,
        )
        .first()
    )
    if not order:
        raise RazorpayError('Payment order not found.', code='order_not_found')

    if order.status == SellerRazorpayOrder.STATUS_PAID:
        tx = customer.transactions.filter(
            transaction_type='payment_received',
            note__icontains=order.reference_id,
        ).first()
        return {
            'message': 'Payment already recorded',
            'reference_id': order.reference_id,
            'transaction_id': str(tx.id) if tx else None,
        }

    if not verify_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    ):
        order.status = SellerRazorpayOrder.STATUS_FAILED
        order.error_message = 'Invalid payment signature'
        order.save(update_fields=['status', 'error_message'])
        raise RazorpayError('Payment verification failed.', code='invalid_signature')

    method = resolve_razorpay_payment_method(razorpay_payment_id)
    tx, _sms = receive_payment(
        seller,
        customer,
        order.amount,
        payment_method=method,
        note=order.note or f'Online payment ({order.reference_id})',
        send_sms=False,
    )

    order.status = SellerRazorpayOrder.STATUS_PAID
    order.razorpay_payment_id = razorpay_payment_id
    order.payment_method = method
    order.paid_at = timezone.now()
    order.save(
        update_fields=[
            'status',
            'razorpay_payment_id',
            'payment_method',
            'paid_at',
        ]
    )

    customer.refresh_from_db()
    from .services import customer_detail

    return {
        'message': 'Payment successful',
        'reference_id': order.reference_id,
        'transaction_id': str(tx.id),
        'customer': customer_detail(customer),
    }


def _customer_contact(customer):
    from customerapp.messaging import normalize_phone

    digits = normalize_phone(customer.phone)
    if len(digits) == 10:
        return f'+91{digits}'
    return customer.phone or ''


@transaction.atomic
def create_seller_payment_link(*, seller, customer, max_amount, note=''):
    """Create Razorpay payment link; customer can pay any amount up to max (partial)."""
    if not razorpay_configured():
        raise RazorpayError(
            'Razorpay is not configured. Set RAZORPAY_TEST_KEY_ID and RAZORPAY_TEST_KEY_SECRET.',
            code='razorpay_not_configured',
        )

    from .models import SellerPaymentLink

    pay_max = _validate_amount(customer, max_amount)
    reference_id = f'SPL-{uuid.uuid4().hex[:12].upper()}'
    expire_at = timezone.now() + timezone.timedelta(days=30)

    payload = {
        'amount': _amount_paise(pay_max),
        'currency': 'INR',
        'accept_partial': True,
        'first_min_partial_amount': 100,
        'description': f'Payment to {seller.business_name}'[:255],
        'customer': {
            'name': customer.name[:50] or 'Customer',
            'contact': _customer_contact(customer),
        },
        'notify': {'sms': False, 'email': False},
        'reminder_enable': False,
        'expire_by': int(expire_at.timestamp()),
        'notes': {
            'type': 'seller_payment_link',
            'reference_id': reference_id,
            'seller_id': str(seller.id),
            'customer_id': str(customer.id),
            'max_amount': str(pay_max),
        },
    }
    email = (customer.email or '').strip()
    if email:
        payload['customer']['email'] = email

    from easyudhar.razorpay_route import (
        attach_transfers_to_payment_link_payload,
        transfers_for_single_seller,
    )

    transfers, transfer_total = transfers_for_single_seller(
        seller, pay_max, percentage=True
    )
    payload = attach_transfers_to_payment_link_payload(payload, transfers)

    rz_link = _razorpay_request('POST', '/payment_links', payload)
    short_url = rz_link.get('short_url', '')
    link_id = rz_link.get('id')
    if not link_id or not short_url:
        raise RazorpayError('Invalid payment link response from Razorpay.', code='api_error')

    link = SellerPaymentLink.objects.create(
        seller=seller,
        customer=customer,
        max_amount=pay_max,
        note=note or '',
        reference_id=reference_id,
        razorpay_payment_link_id=link_id,
        short_url=short_url,
        expire_at=expire_at,
    )

    return {
        'payment_link_id': str(link.id),
        'reference_id': reference_id,
        'short_url': short_url,
        'max_amount': str(pay_max),
        'amount_received': '0',
        'amount_remaining': str(pay_max),
        'partial_payment_allowed': True,
        'expires_at': expire_at.isoformat(),
        'customer_name': customer.name,
        'message': 'Payment link created',
    }


@transaction.atomic
def _settle_payment_link_payment(link, payment_id, amount_paise, method=None):
    """Record one Razorpay payment against a seller payment link."""
    from .models import SellerPaymentLink, SellerPaymentLinkPayment

    if SellerPaymentLinkPayment.objects.filter(razorpay_payment_id=payment_id).exists():
        return {'duplicate': True, 'payment_id': payment_id}

    link = (
        SellerPaymentLink.objects.select_for_update()
        .filter(pk=link.pk)
        .first()
    )
    if not link:
        return {'handled': False, 'reason': 'link_not_found'}

    if link.status in (SellerPaymentLink.STATUS_PAID, SellerPaymentLink.STATUS_CANCELLED):
        return {'handled': True, 'reason': 'link_already_closed'}

    amount = Decimal(str(amount_paise)) / Decimal('100')
    remaining = link.amount_remaining
    if amount <= 0:
        return {'handled': False, 'reason': 'invalid_amount'}
    if amount > remaining:
        amount = remaining

    if method is None:
        method = resolve_razorpay_payment_method(payment_id)
    note = link.note or f'Payment link ({link.reference_id})'
    tx, _sms = receive_payment(
        link.seller,
        link.customer,
        amount,
        payment_method=method,
        note=note,
        send_sms=False,
    )

    SellerPaymentLinkPayment.objects.create(
        payment_link=link,
        razorpay_payment_id=payment_id,
        amount=amount,
        payment_method=method,
    )

    link.amount_received += amount
    if link.amount_received >= link.max_amount:
        link.status = SellerPaymentLink.STATUS_PAID
        link.paid_at = timezone.now()
    else:
        link.status = SellerPaymentLink.STATUS_PARTIAL
    link.save(update_fields=['amount_received', 'status', 'paid_at'])

    return {
        'handled': True,
        'reference_id': link.reference_id,
        'transaction_id': str(tx.id),
        'amount': str(amount),
        'amount_received': str(link.amount_received),
    }


def _payments_for_link(razorpay_payment_link_id):
    from customerapp.razorpay_service import fetch_razorpay_payment

    data = _razorpay_request('GET', f'/payment_links/{razorpay_payment_link_id}')
    captured = []
    seen = set()

    def _add_payment(payment_id, status_hint=None):
        if not payment_id or payment_id in seen:
            return
        try:
            pay = fetch_razorpay_payment(payment_id)
        except RazorpayError:
            return
        pay_status = (pay.get('status') or status_hint or '').lower()
        if pay_status in ('captured', 'paid'):
            seen.add(payment_id)
            captured.append(pay)

    for item in data.get('payments') or []:
        if isinstance(item, dict):
            _add_payment(
                item.get('payment_id') or item.get('id'),
                item.get('status'),
            )
        elif isinstance(item, str):
            _add_payment(item)

    if not captured:
        listed = _razorpay_request(
            'GET',
            f'/payments/?payment_link_id={razorpay_payment_link_id}',
        )
        for pay in listed.get('items') or []:
            if isinstance(pay, dict):
                pay_id = pay.get('id')
                if (pay.get('status') or '').lower() in ('captured', 'paid'):
                    if pay_id and pay_id not in seen:
                        seen.add(pay_id)
                        captured.append(pay)

    return captured, data


@transaction.atomic
def sync_seller_payment_link(link):
    """Poll Razorpay and record any new payments (webhook fallback)."""
    from .models import SellerPaymentLink

    payments, rz_data = _payments_for_link(link.razorpay_payment_link_id)
    settled = []
    for pay in payments:
        payment_id = pay.get('id')
        amount_paise = pay.get('amount') or 0
        if not payment_id:
            continue
        method = razorpay_method_to_standard(pay.get('method'))
        result = _settle_payment_link_payment(
            link,
            payment_id,
            amount_paise,
            method=method,
        )
        if result.get('handled'):
            settled.append(result)
        link = SellerPaymentLink.objects.get(pk=link.pk)

    amount_paid_paise = rz_data.get('amount_paid') or 0
    rz_status = (rz_data.get('status') or '').lower()
    if rz_status in ('expired', 'cancelled'):
        link.status = (
            SellerPaymentLink.STATUS_EXPIRED
            if rz_status == 'expired'
            else SellerPaymentLink.STATUS_CANCELLED
        )
        link.save(update_fields=['status'])

    from .services import customer_detail

    link.customer.refresh_from_db()
    return {
        'payment_link_id': str(link.id),
        'reference_id': link.reference_id,
        'synced_count': len(settled),
        'payments': settled,
        'amount_received': str(link.amount_received),
        'amount_remaining': str(link.amount_remaining),
        'status': link.status,
        'razorpay_amount_paid': str(Decimal(str(amount_paid_paise)) / Decimal('100')),
        'customer': customer_detail(link.customer),
    }


def sync_customer_payment_links(*, seller, customer):
    """Sync all open payment links for a customer."""
    from .models import SellerPaymentLink

    links = SellerPaymentLink.objects.filter(
        seller=seller,
        customer=customer,
        status__in=[
            SellerPaymentLink.STATUS_ACTIVE,
            SellerPaymentLink.STATUS_PARTIAL,
        ],
    ).order_by('-created_at')

    results = []
    total_synced = 0
    for link in links:
        try:
            payload = sync_seller_payment_link(link)
            total_synced += payload.get('synced_count', 0)
            results.append(payload)
        except RazorpayError as exc:
            results.append(
                {
                    'payment_link_id': str(link.id),
                    'reference_id': link.reference_id,
                    'error': exc.message,
                }
            )

    customer.refresh_from_db()
    from .services import customer_detail

    return {
        'synced_count': total_synced,
        'links': results,
        'customer': customer_detail(customer),
    }


def sync_seller_payment_links(seller):
    """Sync all open payment links for a seller (e.g. dashboard refresh)."""
    from .models import SellerPaymentLink

    links = (
        SellerPaymentLink.objects.filter(
            seller=seller,
            status__in=[
                SellerPaymentLink.STATUS_ACTIVE,
                SellerPaymentLink.STATUS_PARTIAL,
            ],
        )
        .select_related('customer')
        .order_by('-created_at')
    )

    total_synced = 0
    results = []
    for link in links:
        try:
            payload = sync_seller_payment_link(link)
            total_synced += payload.get('synced_count', 0)
            results.append(payload)
        except RazorpayError as exc:
            results.append(
                {
                    'payment_link_id': str(link.id),
                    'reference_id': link.reference_id,
                    'error': exc.message,
                }
            )

    return {
        'synced_count': total_synced,
        'links': results,
    }


@transaction.atomic
def settle_seller_payment_link_webhook(payload):
    """Record ledger payment when customer pays via Razorpay payment link."""
    from .models import SellerPaymentLink

    pay_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
    pl_entity = payload.get('payload', {}).get('payment_link', {}).get('entity', {})

    pl_id = pl_entity.get('id') or pay_entity.get('payment_link_id')
    payment_id = pay_entity.get('id')
    amount_paise = pay_entity.get('amount') or 0

    if not pl_id or not payment_id:
        return {'handled': False, 'reason': 'missing_ids'}

    link = (
        SellerPaymentLink.objects.select_for_update()
        .filter(razorpay_payment_link_id=pl_id)
        .first()
    )
    if not link:
        return {'handled': False, 'reason': 'seller_payment_link_not_found'}

    method = razorpay_method_to_standard(pay_entity.get('method'))
    result = _settle_payment_link_payment(
        link,
        payment_id,
        amount_paise,
        method=method,
    )
    result['event'] = payload.get('event', '')
    return result


def settle_seller_payment_link_from_payment_entity(pay_entity):
    """Handle payment.captured where payment belongs to a payment link."""
    from .models import SellerPaymentLink

    pl_id = pay_entity.get('payment_link_id')
    payment_id = pay_entity.get('id')
    amount_paise = pay_entity.get('amount') or 0
    if not pl_id or not payment_id:
        return {'handled': False, 'reason': 'missing_payment_link_id'}

    link = (
        SellerPaymentLink.objects.select_for_update()
        .filter(razorpay_payment_link_id=pl_id)
        .first()
    )
    if not link:
        return {'handled': False, 'reason': 'seller_payment_link_not_found'}

    method = razorpay_method_to_standard(pay_entity.get('method'))
    result = _settle_payment_link_payment(
        link,
        payment_id,
        amount_paise,
        method=method,
    )
    result['event'] = 'payment.captured'
    return result
