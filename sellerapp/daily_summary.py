from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import LedgerTransaction, Seller, SellerCustomer, SellerNotification, SellerSettings
from .nimbus_sms import send_summary_sms
from .notifications import notify_seller_general
from .services import _transaction_effective_date


def _parse_hhmm(value):
    try:
        hour, minute = value.split(':')
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        return 21, 0


def is_summary_due_now(settings_row, now=None):
    now = now or timezone.localtime()
    hour, minute = _parse_hhmm(settings_row.daily_summary_time)
    return now.hour == hour and now.minute < 15


def build_seller_summary(seller):
    customers = SellerCustomer.objects.filter(seller=seller)
    outstanding = customers.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')
    overdue_qs = customers.filter(status=SellerCustomer.STATUS_OVERDUE)
    overdue_count = overdue_qs.count()
    overdue_amount = overdue_qs.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')

    today = timezone.localdate()
    today_collection = Decimal('0')
    for tx in LedgerTransaction.objects.filter(
        seller=seller,
        transaction_type=LedgerTransaction.TYPE_PAYMENT,
    ).only('amount', 'created_at', 'device_created_at'):
        if _transaction_effective_date(tx) == today:
            today_collection += tx.amount

    top_overdue = overdue_qs.order_by('-outstanding_amount').first()
    top_line = ''
    if top_overdue:
        top_line = f' Top: {top_overdue.name} Rs.{top_overdue.outstanding_amount}.'

    text = (
        f'EazyUdhar: Today Rs.{today_collection} collected. '
        f'Outstanding Rs.{outstanding}. {overdue_count} overdue.{top_line} '
        f'- {seller.business_name}'
    )
    return {
        'today_collection': today_collection,
        'outstanding': outstanding,
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
        'text': text,
    }


def send_daily_summary_for_seller(seller, *, force=False):
    if not seller.is_active:
        return {'skipped': True, 'reason': 'seller suspended'}

    settings, _ = SellerSettings.objects.get_or_create(seller=seller)
    if not settings.daily_summary_enabled and not force:
        return {'skipped': True, 'reason': 'disabled'}

    now = timezone.localtime()
    if not force and not is_summary_due_now(settings, now):
        return {'skipped': True, 'reason': 'not scheduled time'}

    summary = build_seller_summary(seller)
    channels = [c.lower() for c in (settings.daily_summary_channels or ['sms', 'push'])]
    results = {'channels': {}, 'summary': summary}

    if 'sms' in channels:
        results['channels']['sms'] = send_summary_sms(seller=seller, text=summary['text'])

    if 'push' in channels:
        notification = notify_seller_general(
            seller,
            title='Daily business summary',
            subtitle=summary['text'][:500],
            notification_type=SellerNotification.TYPE_DAILY_SUMMARY,
        )
        results['channels']['push'] = {
            'sent': notification is not None,
            'notification_id': str(notification.id) if notification else '',
        }

    return results


def run_daily_summaries(*, force=False):
    results = []
    # Only active (non-suspended) sellers.
    for seller in Seller.objects.filter(is_active=True):
        try:
            row = send_daily_summary_for_seller(seller, force=force)
            results.append({'seller': seller.business_name, **row})
        except Exception as exc:
            results.append({'seller': seller.business_name, 'error': str(exc)})
    return results
