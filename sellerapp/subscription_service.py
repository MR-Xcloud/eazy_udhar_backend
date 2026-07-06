"""Seller subscription trial, plans catalog, and platform Razorpay billing."""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from adminapp.models import RazorpayPayment, SellerSubscription, SubscriptionPlan
from customerapp.razorpay_service import (
    RazorpayError,
    _amount_paise,
    _razorpay_request,
    razorpay_configured,
    verify_payment_signature,
)
from easyudhar.razorpay_config import get_razorpay_credentials

from .models import SellerSubscriptionOrder

TRIAL_DAYS = 7


class SubscriptionQuotaError(Exception):
    def __init__(self, message, *, code='message_quota_exceeded', quota=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.quota = quota or {}


def _plan_features(plan):
    raw = plan.features
    return raw if isinstance(raw, dict) else {}


def _is_purchasable(plan):
    features = _plan_features(plan)
    if features.get('purchasable') is False:
        return False
    return plan.price_monthly > 0 or plan.price_yearly > 0


def _days_until(dt, *, now=None):
    now = now or timezone.now()
    if dt is None:
        return 0
    if dt <= now:
        return 0
    delta = dt.date() - now.date()
    return max(delta.days, 1 if dt > now else 0)


def _expire_if_needed(sub, *, now=None):
    now = now or timezone.now()
    if sub.status == SellerSubscription.STATUS_TRIAL:
        end = sub.trial_ends_at or sub.current_period_end
        if end and end < now:
            sub.status = SellerSubscription.STATUS_EXPIRED
            sub.save(update_fields=['status'])
    elif sub.status == SellerSubscription.STATUS_ACTIVE:
        if sub.current_period_end < now:
            sub.status = SellerSubscription.STATUS_EXPIRED
            sub.save(update_fields=['status'])
    return sub


def get_current_subscription(seller):
    sub = (
        SellerSubscription.objects.filter(seller=seller)
        .select_related('plan')
        .order_by('-created_at')
        .first()
    )
    if sub is None:
        return None
    return _expire_if_needed(sub)


def _subscription_period_bounds(sub):
    if sub is None:
        return None, None
    start = sub.current_period_start
    if sub.status == SellerSubscription.STATUS_TRIAL:
        end = sub.trial_ends_at or sub.current_period_end
    else:
        end = sub.current_period_end
    return start, end


def count_messages_used(seller, period_start, period_end):
    from customerapp.models import ShopMessage

    from .models import ReminderLog

    if not period_start or not period_end:
        return 0

    reminder_count = ReminderLog.objects.filter(
        seller=seller,
        success=True,
        channel__in=[ReminderLog.CHANNEL_SMS, ReminderLog.CHANNEL_WHATSAPP],
        sent_at__gte=period_start,
        sent_at__lte=period_end,
    ).count()

    chat_count = ShopMessage.objects.filter(
        seller=seller,
        sender=ShopMessage.SENDER_SELLER,
        created_at__gte=period_start,
        created_at__lte=period_end,
    ).filter(attachment='').count()

    return reminder_count + chat_count


def message_quota_dict(seller):
    from .sms_pack_service import get_sms_pack_balance

    sub = get_current_subscription(seller)
    if sub is None:
        return {
            'message_limit': 0,
            'messages_used': 0,
            'messages_remaining': 0,
            'sms_pack_balance': 0,
            'total_messages_remaining': 0,
        }

    limit = int(_plan_features(sub.plan).get('message_limit', 0))
    start, end = _subscription_period_bounds(sub)
    used = count_messages_used(seller, start, end)
    plan_remaining = max(0, limit - used) if limit > 0 else 0
    pack_balance = get_sms_pack_balance(seller)
    return {
        'message_limit': limit,
        'messages_used': used,
        'messages_remaining': plan_remaining,
        'sms_pack_balance': pack_balance,
        'total_messages_remaining': plan_remaining + pack_balance,
    }


def _sms_credits_from_pack(seller, sms_count):
    """How many of [sms_count] sends must draw from prepaid SMS pack balance."""
    sms_count = int(sms_count)
    if sms_count <= 0:
        return 0
    quota = message_quota_dict(seller)
    plan_remaining = quota['messages_remaining']
    return max(0, sms_count - plan_remaining)


def consume_message_credits_after_send(seller, *, sms=0, other=0):
    """After a successful send, deduct prepaid SMS credits if plan quota is exhausted."""
    pack_needed = _sms_credits_from_pack(seller, sms)
    if pack_needed > 0:
        from .sms_pack_service import consume_sms_pack_credit

        consume_sms_pack_credit(seller, pack_needed)
    # `other` (WhatsApp/chat) only consumes plan quota via usage counters.


def assert_can_send_messages(seller, *, count=1, sms_count=None, other_count=None):
    if sms_count is None and other_count is None:
        other_count = count
        sms_count = 0
    else:
        sms_count = int(sms_count or 0)
        other_count = int(other_count or 0)

    quota = message_quota_dict(seller)
    limit = quota['message_limit']
    plan_remaining = quota['messages_remaining']
    pack_balance = quota['sms_pack_balance']

    if limit <= 0 and sms_count + other_count > 0:
        raise SubscriptionQuotaError(
            'Your plan does not include outbound messages. Upgrade to send SMS, '
            'WhatsApp, or chat messages.',
            quota=quota,
        )

    sms_from_plan = min(sms_count, plan_remaining)
    plan_after_sms = plan_remaining - sms_from_plan
    sms_from_pack = sms_count - sms_from_plan

    if sms_from_pack > pack_balance:
        raise SubscriptionQuotaError(
            f"Message limit reached ({quota['messages_used']} of {limit} used). "
            'Buy an SMS pack or upgrade your plan for more messages.',
            quota=quota,
        )
    if other_count > plan_after_sms:
        raise SubscriptionQuotaError(
            f"Message limit reached ({quota['messages_used']} of {limit} used). "
            'Buy an SMS pack or upgrade your plan for more messages.',
            quota=quota,
        )
    return quota


@transaction.atomic
def start_seller_trial(seller):
    if SellerSubscription.objects.filter(seller=seller).exists():
        return get_current_subscription(seller)

    plan = SubscriptionPlan.objects.filter(
        slug='growth-best-value', is_active=True
    ).first()
    if plan is None:
        plan = (
            SubscriptionPlan.objects.filter(is_active=True, price_monthly__gt=0)
            .order_by('sort_order')
            .first()
        )
    if plan is None:
        return None

    now = timezone.now()
    trial_end = now + timedelta(days=TRIAL_DAYS)
    return SellerSubscription.objects.create(
        seller=seller,
        plan=plan,
        status=SellerSubscription.STATUS_TRIAL,
        billing_amount=Decimal('0'),
        current_period_start=now,
        current_period_end=trial_end,
        trial_ends_at=trial_end,
    )


def plan_to_dict(plan):
    features = _plan_features(plan)
    reminder_type = features.get('reminder_type', 'on_demand')
    return {
        'id': plan.id,
        'name': plan.name,
        'slug': plan.slug,
        'price_monthly': float(plan.price_monthly),
        'price_yearly': float(plan.price_yearly),
        'message_limit': int(features.get('message_limit', 0)),
        'reminder_type': reminder_type,
        'reminder_label': features.get(
            'reminder_label',
            'On-demand reminders'
            if reminder_type == 'on_demand'
            else 'Automated daily reminders',
        ),
        'badge': features.get('badge', ''),
        'is_free': bool(features.get('is_free', False)),
        'purchasable': _is_purchasable(plan),
        'sort_order': plan.sort_order,
    }


def list_purchasable_plans():
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('sort_order', 'name')
    return [plan_to_dict(p) for p in plans if _is_purchasable(p)]


def subscription_status_payload(seller):
    sub = get_current_subscription(seller)
    now = timezone.now()
    if sub is None:
        return {
            'status': 'none',
            'plan_name': None,
            'plan_slug': None,
            'is_trial': False,
            'is_active': False,
            'trial_days_remaining': 0,
            'days_remaining': 0,
            'expires_at': None,
            'message_limit': 0,
            'messages_used': 0,
            'messages_remaining': 0,
            'sms_pack_balance': 0,
            'total_messages_remaining': 0,
            'reminder_type': 'on_demand',
            'billing_cycle': None,
        }

    features = _plan_features(sub.plan)
    is_trial = sub.status == SellerSubscription.STATUS_TRIAL
    expires_at = sub.trial_ends_at if is_trial else sub.current_period_end
    days_remaining = _days_until(expires_at, now=now)

    billing_cycle = None
    if sub.status == SellerSubscription.STATUS_ACTIVE:
        latest_paid = (
            SellerSubscriptionOrder.objects.filter(
                seller=seller,
                status=SellerSubscriptionOrder.STATUS_PAID,
            )
            .order_by('-paid_at')
            .first()
        )
        if latest_paid:
            billing_cycle = latest_paid.billing_cycle

    quota = message_quota_dict(seller)
    return {
        'status': sub.status,
        'plan_name': sub.plan.name,
        'plan_slug': sub.plan.slug,
        'is_trial': is_trial,
        'is_active': sub.status == SellerSubscription.STATUS_ACTIVE,
        'trial_days_remaining': days_remaining if is_trial else 0,
        'days_remaining': days_remaining,
        'expires_at': expires_at.isoformat() if expires_at else None,
        'message_limit': quota['message_limit'],
        'messages_used': quota['messages_used'],
        'messages_remaining': quota['messages_remaining'],
        'sms_pack_balance': quota['sms_pack_balance'],
        'total_messages_remaining': quota['total_messages_remaining'],
        'reminder_type': features.get('reminder_type', 'on_demand'),
        'billing_cycle': billing_cycle,
    }


def _plan_amount(plan, billing_cycle):
    if billing_cycle == SellerSubscriptionOrder.CYCLE_YEARLY:
        amount = plan.price_yearly
    else:
        amount = plan.price_monthly
    amount = Decimal(str(amount))
    if amount <= 0:
        raise RazorpayError('This plan is not available for purchase.', code='invalid_plan')
    return amount


@transaction.atomic
def create_subscription_order(*, seller, plan_slug, billing_cycle):
    if not razorpay_configured():
        raise RazorpayError(
            'Razorpay is not configured.',
            code='razorpay_not_configured',
        )

    billing_cycle = (billing_cycle or '').strip().lower()
    if billing_cycle not in (
        SellerSubscriptionOrder.CYCLE_MONTHLY,
        SellerSubscriptionOrder.CYCLE_YEARLY,
    ):
        raise RazorpayError(
            'billing_cycle must be monthly or yearly.',
            code='invalid_billing_cycle',
        )

    plan = SubscriptionPlan.objects.filter(slug=plan_slug, is_active=True).first()
    if plan is None or not _is_purchasable(plan):
        raise RazorpayError('Subscription plan not found.', code='invalid_plan')

    amount = _plan_amount(plan, billing_cycle)
    reference_id = f'SUB-{uuid.uuid4().hex[:12].upper()}'
    amount_paise = _amount_paise(amount)

    order_payload = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': reference_id,
        'notes': {
            'type': 'seller_subscription',
            'seller_id': str(seller.id),
            'plan_slug': plan.slug,
            'billing_cycle': billing_cycle,
        },
    }
    rz_order = _razorpay_request('POST', '/orders', order_payload)

    SellerSubscriptionOrder.objects.create(
        seller=seller,
        plan_slug=plan.slug,
        plan_name=plan.name,
        billing_cycle=billing_cycle,
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
        'plan_slug': plan.slug,
        'plan_name': plan.name,
        'billing_cycle': billing_cycle,
        'amount_display': float(amount),
    }


@transaction.atomic
def verify_subscription_payment(
    *,
    seller,
    plan_slug,
    billing_cycle,
    razorpay_order_id,
    razorpay_payment_id,
    razorpay_signature,
):
    order = (
        SellerSubscriptionOrder.objects.select_for_update()
        .filter(
            seller=seller,
            razorpay_order_id=razorpay_order_id,
            plan_slug=plan_slug,
            billing_cycle=billing_cycle,
        )
        .first()
    )
    if order is None:
        raise RazorpayError('Subscription order not found.', code='order_not_found')

    if order.status == SellerSubscriptionOrder.STATUS_PAID:
        sub = get_current_subscription(seller)
        return {
            'message': 'Subscription already active',
            'subscription': subscription_status_payload(seller),
            'plan_slug': sub.plan.slug if sub else plan_slug,
        }

    if not verify_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    ):
        order.status = SellerSubscriptionOrder.STATUS_FAILED
        order.error_message = 'Invalid payment signature'
        order.save(update_fields=['status', 'error_message'])
        raise RazorpayError('Payment verification failed.', code='invalid_signature')

    plan = SubscriptionPlan.objects.filter(slug=plan_slug, is_active=True).first()
    if plan is None:
        raise RazorpayError('Subscription plan not found.', code='invalid_plan')

    now = timezone.now()
    if billing_cycle == SellerSubscriptionOrder.CYCLE_YEARLY:
        period_end = now + timedelta(days=365)
    else:
        period_end = now + timedelta(days=30)

    SellerSubscription.objects.filter(seller=seller).exclude(
        status=SellerSubscription.STATUS_CANCELLED
    ).update(status=SellerSubscription.STATUS_EXPIRED)

    SellerSubscription.objects.create(
        seller=seller,
        plan=plan,
        status=SellerSubscription.STATUS_ACTIVE,
        billing_amount=order.amount,
        current_period_start=now,
        current_period_end=period_end,
        trial_ends_at=None,
    )

    order.status = SellerSubscriptionOrder.STATUS_PAID
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
        method='subscription',
    )

    return {
        'message': 'Subscription activated',
        'subscription': subscription_status_payload(seller),
        'plan_slug': plan.slug,
        'plan_name': plan.name,
        'billing_cycle': billing_cycle,
    }
