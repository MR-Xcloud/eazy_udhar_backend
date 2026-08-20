from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from customerapp.models import Customer
from sellerapp.models import LedgerTransaction, ReminderLog, Seller, SellerCustomer
from sellerapp.services import _transaction_effective_date

from adminapp.models import SellerSubscription


def _float_amount(value):
    return float(value or 0)


def dashboard_stats():
    today = timezone.localdate()
    sellers = Seller.objects.all()
    customers = Customer.objects.all()
    seller_customers = SellerCustomer.objects.all()

    outstanding_total = seller_customers.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')
    overdue_qs = seller_customers.filter(status=SellerCustomer.STATUS_OVERDUE)
    overdue_amount = overdue_qs.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')

    today_collection = Decimal('0')
    for tx in LedgerTransaction.objects.filter(
        transaction_type=LedgerTransaction.TYPE_PAYMENT
    ).only('amount', 'created_at', 'device_created_at'):
        if _transaction_effective_date(tx) == today:
            today_collection += tx.amount

    yesterday_collection = Decimal('0')
    yesterday = today - timedelta(days=1)
    for tx in LedgerTransaction.objects.filter(
        transaction_type=LedgerTransaction.TYPE_PAYMENT
    ).only('amount', 'created_at', 'device_created_at'):
        if _transaction_effective_date(tx) == yesterday:
            yesterday_collection += tx.amount

    change_pct = None
    if yesterday_collection > 0:
        change_pct = round(
            float((today_collection - yesterday_collection) / yesterday_collection * 100),
            1,
        )

    sms_today = ReminderLog.objects.filter(
        channel=ReminderLog.CHANNEL_SMS, sent_at__date=today
    )
    reminders_today = ReminderLog.objects.filter(sent_at__date=today)

    trials_active = SellerSubscription.objects.filter(status=SellerSubscription.STATUS_TRIAL).count()
    subs_active = SellerSubscription.objects.filter(
        status=SellerSubscription.STATUS_ACTIVE
    ).count()

    mrr = SellerSubscription.objects.filter(
        status=SellerSubscription.STATUS_ACTIVE
    ).aggregate(t=Sum('billing_amount'))['t'] or Decimal('0')

    return {
        'sellers_total': sellers.count(),
        'sellers_active': sellers.filter(is_active=True).count(),
        'sellers_suspended': sellers.filter(is_active=False).count(),
        'customers_total': customers.count(),
        'customers_active': customers.filter(is_active=True).count(),
        'customers_suspended': customers.filter(is_active=False).count(),
        'outstanding_total': _float_amount(outstanding_total),
        'collections_today': _float_amount(today_collection),
        'collections_change_pct': change_pct,
        'overdue_customers': overdue_qs.count(),
        'overdue_amount': _float_amount(overdue_amount),
        'trials_active': trials_active,
        'subscriptions_active': subs_active,
        'mrr': _float_amount(mrr),
        'arr': _float_amount(mrr * 12),
        'sms_sent_today': sms_today.filter(success=True).count(),
        'reminders_sent_today': reminders_today.filter(success=True).count(),
        'sms_failed_today': sms_today.filter(success=False).count(),
        'push_failed_today': ReminderLog.objects.filter(
            channel=ReminderLog.CHANNEL_PUSH, sent_at__date=today, success=False
        ).count(),
    }


def _parse_range(range_param):
    mapping = {'7d': 7, '30d': 30, '90d': 90}
    return mapping.get((range_param or '30d').lower(), 30)


def collections_chart(range_param='30d'):
    days = _parse_range(range_param)
    start = timezone.localdate() - timedelta(days=days - 1)
    buckets = {}
    for i in range(days):
        d = start + timedelta(days=i)
        buckets[d.isoformat()] = {'date': d.isoformat(), 'collections': 0.0, 'credits': 0.0}

    for tx in LedgerTransaction.objects.filter(created_at__date__gte=start):
        key = _transaction_effective_date(tx).isoformat()
        if key not in buckets:
            continue
        amount = float(tx.amount)
        if tx.transaction_type == LedgerTransaction.TYPE_PAYMENT:
            buckets[key]['collections'] += amount
        elif tx.transaction_type == LedgerTransaction.TYPE_CREDIT:
            buckets[key]['credits'] += amount

    return {'data': list(buckets.values())}


def signups_chart(range_param='30d'):
    days = _parse_range(range_param)
    if days > 30:
        days = 30
    start = timezone.localdate() - timedelta(days=days - 1)
    buckets = {}
    for i in range(days):
        d = start + timedelta(days=i)
        buckets[d.isoformat()] = {'date': d.isoformat(), 'sellers': 0, 'customers': 0}

    for row in (
        Seller.objects.filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(c=Count('id'))
    ):
        key = row['day'].isoformat()
        if key in buckets:
            buckets[key]['sellers'] = row['c']

    for row in (
        Customer.objects.filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(c=Count('id'))
    ):
        key = row['day'].isoformat()
        if key in buckets:
            buckets[key]['customers'] = row['c']

    return {'data': list(buckets.values())}


def outstanding_by_status():
    qs = SellerCustomer.objects.values('status').annotate(value=Count('id'))
    name_map = {
        SellerCustomer.STATUS_PENDING: 'Pending',
        SellerCustomer.STATUS_OVERDUE: 'Overdue',
        SellerCustomer.STATUS_SETTLED: 'Settled',
        SellerCustomer.STATUS_PAID: 'Settled',
    }
    merged = {}
    for row in qs:
        name = name_map.get(row['status'], row['status'].title())
        merged[name] = merged.get(name, 0) + row['value']
    return {'data': [{'name': k, 'value': v} for k, v in merged.items()]}


def recent_activity(limit=20):
    items = []
    for tx in LedgerTransaction.objects.select_related(
        'seller', 'customer'
    ).order_by('-created_at')[:limit]:
        label = tx.get_transaction_type_display()
        items.append(
            {
                'type': tx.transaction_type,
                'title': f'{label} — Rs.{tx.amount}',
                'who': f'{tx.customer.name} @ {tx.seller.business_name}',
                'time': tx.effective_at.isoformat(),
                'tone': 'positive' if tx.transaction_type == LedgerTransaction.TYPE_PAYMENT else 'neutral',
            }
        )
    return {'data': items}
