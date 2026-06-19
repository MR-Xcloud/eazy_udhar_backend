"""Razorpay order creation, signature verification, and ledger settlement."""

import base64
import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from easyudhar.payment_utils import normalize_payment_method, razorpay_method_to_standard

from easyudhar.razorpay_config import get_razorpay_credentials

from .models import CustomerAccount, RazorpayPaymentOrder
from .services import process_payment

RAZORPAY_API_BASE = 'https://api.razorpay.com/v1'


class RazorpayError(Exception):
    def __init__(self, message, code='razorpay_error'):
        super().__init__(message)
        self.message = message
        self.code = code


def razorpay_configured():
    key_id, key_secret, _ = get_razorpay_credentials()
    return bool(key_id and key_secret)


def _auth_header():
    key_id, key_secret, _ = get_razorpay_credentials()
    token = base64.b64encode(f'{key_id}:{key_secret}'.encode()).decode()
    return f'Basic {token}'


def _razorpay_request(method, path, payload=None):
    url = f'{RAZORPAY_API_BASE}{path}'
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            'Authorization': _auth_header(),
            'Content-Type': 'application/json',
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode('utf-8')
            return json.loads(body) if body else {}
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RazorpayError(f'Razorpay API error: {detail or exc.reason}', code='api_error') from exc
    except URLError as exc:
        raise RazorpayError(f'Razorpay network error: {exc.reason}', code='network_error') from exc


def _amount_paise(amount):
    return int(Decimal(str(amount)) * 100)


def _parse_payment_targets(user, shop_id, shop_ids):
    account = None
    ids = [str(s) for s in (shop_ids or []) if s]
    if shop_id and not ids:
        account = CustomerAccount.objects.filter(id=shop_id, user=user).first()
        if not account:
            raise RazorpayError('Shop account not found.', code='invalid_shop')
        return account, [str(shop_id)], [account]
    targets = list(
        CustomerAccount.objects.filter(user=user, id__in=ids, has_balance=True)
    )
    if not targets:
        raise RazorpayError('No valid shop accounts found for payment.', code='invalid_shop')
    return account, ids, targets


def validate_payment_amount(user, shop_id, shop_ids, amount):
    account, ids, targets = _parse_payment_targets(user, shop_id, shop_ids)
    pay_amount = Decimal(str(amount))
    if pay_amount <= 0:
        raise RazorpayError('Amount must be greater than zero.', code='invalid_amount')
    max_due = sum((t.outstanding_amount for t in targets), Decimal('0'))
    single_shop = account is not None or len(targets) == 1
    if not single_shop and pay_amount > max_due:
        raise RazorpayError(
            f'Amount exceeds outstanding balance (max Rs.{max_due}).',
            code='amount_exceeds_due',
        )
    if single_shop and pay_amount < max_due and max_due > 0:
        pass
    return account, ids, targets, pay_amount


@transaction.atomic
def create_razorpay_order(*, user, shop_id=None, shop_ids=None, amount):
    if not razorpay_configured():
        raise RazorpayError(
            'Razorpay is not configured. Set RAZORPAY_TEST_KEY_ID and RAZORPAY_TEST_KEY_SECRET.',
            code='razorpay_not_configured',
        )

    account, ids, targets, pay_amount = validate_payment_amount(
        user, shop_id, shop_ids, amount
    )
    reference_id = f'PAY-{uuid.uuid4().hex[:12].upper()}'
    rz_order = _razorpay_request(
        'POST',
        '/orders',
        {
            'amount': _amount_paise(pay_amount),
            'currency': 'INR',
            'receipt': reference_id,
            'notes': {
                'customer_id': str(user.id),
                'shop_ids': ','.join(ids),
            },
        },
    )

    RazorpayPaymentOrder.objects.create(
        user=user,
        amount=pay_amount,
        shop_ids=ids,
        account_id=account.id if account else None,
        reference_id=reference_id,
        razorpay_order_id=rz_order['id'],
        status=RazorpayPaymentOrder.STATUS_PENDING,
    )
    key_id, _, _ = get_razorpay_credentials()
    max_payable = sum((t.outstanding_amount for t in targets), Decimal('0'))
    return {
        'order_id': rz_order['id'],
        'amount': _amount_paise(pay_amount),
        'currency': 'INR',
        'key_id': key_id,
        'reference_id': reference_id,
        'mode': settings.RAZORPAY_MODE,
        'max_payable': str(max_payable),
        'allow_excess_payment': len(targets) == 1,
        'is_partial': pay_amount < max_payable,
        'partial_payment_allowed': True,
    }


def fetch_razorpay_payment(payment_id):
    return _razorpay_request('GET', f'/payments/{payment_id}')


def resolve_razorpay_payment_method(payment_id):
    try:
        data = fetch_razorpay_payment(payment_id)
        return razorpay_method_to_standard(data.get('method'))
    except RazorpayError:
        return normalize_payment_method('upi')


def verify_payment_signature(order_id, payment_id, signature):
    _, key_secret, _ = get_razorpay_credentials()
    body = f'{order_id}|{payment_id}'
    expected = hmac.new(
        key_secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def verify_webhook_signature(body_text, signature):
    _, _, webhook_secret = get_razorpay_credentials()
    if not webhook_secret:
        return False
    expected = hmac.new(
        webhook_secret.encode('utf-8'),
        body_text.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def _settle_order(order, payment_id, method=None):
    if order.status == RazorpayPaymentOrder.STATUS_PAID:
        payments = list(order.user.payments.filter(reference_id=order.reference_id))
        return payments, order.reference_id

    if method is None:
        method = resolve_razorpay_payment_method(payment_id)
    method = normalize_payment_method(method)

    account = None
    if order.account_id:
        account = CustomerAccount.objects.filter(id=order.account_id, user=order.user).first()

    payments, reference_id = process_payment(
        order.user,
        shop_ids=order.shop_ids,
        amount=order.amount,
        method=method,
        account=account,
        reference_id=order.reference_id,
        razorpay_order_id=order.razorpay_order_id,
        razorpay_payment_id=payment_id,
    )
    order.status = RazorpayPaymentOrder.STATUS_PAID
    order.razorpay_payment_id = payment_id
    order.payment_method = method
    order.paid_at = timezone.now()
    order.save(update_fields=['status', 'razorpay_payment_id', 'payment_method', 'paid_at'])
    return payments, reference_id


@transaction.atomic
def verify_and_settle_payment(*, user, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    try:
        order = RazorpayPaymentOrder.objects.select_for_update().get(
            razorpay_order_id=razorpay_order_id,
            user=user,
        )
    except RazorpayPaymentOrder.DoesNotExist:
        raise RazorpayError('Payment order not found.', code='order_not_found')

    if order.status == RazorpayPaymentOrder.STATUS_PAID:
        payments = list(order.user.payments.filter(reference_id=order.reference_id))
        return payments, order.reference_id

    if not verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        order.status = RazorpayPaymentOrder.STATUS_FAILED
        order.error_message = 'Invalid payment signature.'
        order.save(update_fields=['status', 'error_message'])
        raise RazorpayError('Invalid payment signature.', code='invalid_signature')

    return _settle_order(order, razorpay_payment_id)


def handle_razorpay_webhook(body_bytes, signature_header):
    body_text = body_bytes.decode('utf-8')
    if not verify_webhook_signature(body_text, signature_header):
        raise RazorpayError('Invalid webhook signature.', code='invalid_webhook_signature')

    payload = json.loads(body_text)
    event = payload.get('event', '')

    if event in ('payment_link.paid', 'payment_link.partially_paid'):
        try:
            from sellerapp.seller_razorpay_service import settle_seller_payment_link_webhook

            return settle_seller_payment_link_webhook(payload)
        except Exception as exc:
            return {'handled': False, 'event': event, 'error': str(exc)}

    if event == 'payment.captured':
        entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        if entity.get('payment_link_id'):
            try:
                from sellerapp.seller_razorpay_service import (
                    settle_seller_payment_link_from_payment_entity,
                )

                return settle_seller_payment_link_from_payment_entity(entity)
            except Exception as exc:
                return {'handled': False, 'event': event, 'error': str(exc)}

        order_id = entity.get('order_id')
        payment_id = entity.get('id')
        method = razorpay_method_to_standard(entity.get('method'))
        if not order_id or not payment_id:
            return {'handled': False, 'event': event}

        with transaction.atomic():
            try:
                order = RazorpayPaymentOrder.objects.select_for_update().get(
                    razorpay_order_id=order_id,
                )
            except RazorpayPaymentOrder.DoesNotExist:
                return {'handled': False, 'event': event, 'reason': 'order_not_found'}

            if order.status == RazorpayPaymentOrder.STATUS_PAID:
                return {'handled': True, 'event': event, 'reference_id': order.reference_id}

            payments, reference_id = _settle_order(order, payment_id, method=method)
            return {
                'handled': True,
                'event': event,
                'reference_id': reference_id,
                'payments_count': len(payments),
            }

    return {'handled': False, 'event': event}
