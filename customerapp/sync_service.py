from django.utils import timezone
from django.utils.dateparse import parse_datetime

from sellerapp.models import LedgerTransaction
from sellerapp.services import transaction_item

from .models import CustomerAccount, CustomerNotification
from .serializers import CustomerAccountSerializer


class CustomerSyncError(Exception):
    def __init__(self, message, code='validation', status_code=422):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def parse_since(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        raise CustomerSyncError('Invalid since timestamp.')
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def pull_customer_changes(user, since=None):
    since_dt = parse_since(since) if since else None
    synced_at = timezone.now()

    accounts_qs = CustomerAccount.objects.filter(user=user).select_related(
        'seller_customer', 'seller'
    )
    if since_dt:
        accounts_qs = accounts_qs.filter(updated_at__gte=since_dt)

    accounts = list(accounts_qs.order_by('-updated_at'))
    account_data = CustomerAccountSerializer(accounts, many=True).data

    transactions = []
    seller_customer_ids = [
        a.seller_customer_id for a in accounts if a.seller_customer_id
    ]
    if seller_customer_ids:
        txs_qs = LedgerTransaction.objects.filter(
            customer_id__in=seller_customer_ids
        ).select_related('customer')
        if since_dt:
            txs_qs = txs_qs.filter(updated_at__gte=since_dt)
        transactions = [transaction_item(tx) for tx in txs_qs.order_by('-updated_at')]

    unread_notifications = CustomerNotification.objects.filter(
        user=user, is_read=False
    ).count()

    return {
        'synced_at': synced_at.isoformat(),
        'accounts': account_data,
        'transactions': transactions,
        'unread_notifications_count': unread_notifications,
    }
