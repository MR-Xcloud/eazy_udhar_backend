import secrets
from decimal import Decimal

from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone

from .models import CustomerDayDigest, LedgerTransaction


def statement_link(token):
    base = settings.PUBLIC_STATEMENT_BASE_URL.rstrip('/')
    return f'{base}/{token}'


def record_daily_activity(customer, transaction):
    """
    Queue customer for tonight's digest SMS instead of sending per transaction.
    Returns the digest row for today (created or updated).
    """
    activity_date = timezone.localdate()
    digest, _created = CustomerDayDigest.objects.get_or_create(
        seller_customer=customer,
        activity_date=activity_date,
        defaults={'token': secrets.token_urlsafe(16)},
    )
    amount = Decimal(str(transaction.amount))
    if transaction.transaction_type == LedgerTransaction.TYPE_CREDIT:
        digest.credit_total += amount
    elif transaction.transaction_type == LedgerTransaction.TYPE_PAYMENT:
        digest.payment_total += amount
    digest.transaction_count += 1
    digest.save(
        update_fields=[
            'credit_total',
            'payment_total',
            'transaction_count',
            'updated_at',
        ]
    )
    return digest


def queued_sms_result(digest):
    return {
        'sent': False,
        'queued': True,
        'message': 'SMS queued for nightly digest',
        'digest_token': digest.token,
        'statement_url': statement_link(digest.token),
        'message_id': '',
        'error': '',
        'raw_response': '',
    }


def send_pending_digests(*, activity_date=None, force=False):
    """
    Send one digest SMS per customer for the given activity date.
    Intended to run once nightly via cron (e.g. Render cron job).
    """
    from .nimbus_sms import nimbus_sms_configured, send_daily_digest_sms

    if activity_date is None:
        activity_date = timezone.localdate()

    qs = CustomerDayDigest.objects.filter(
        activity_date=activity_date,
        transaction_count__gt=0,
    ).select_related('seller_customer', 'seller_customer__seller')
    if not force:
        qs = qs.filter(sms_sent_at__isnull=True)

    results = []
    for digest in qs:
        customer = digest.seller_customer
        seller = customer.seller
        if not nimbus_sms_configured():
            results.append(
                {
                    'digest_id': str(digest.id),
                    'customer': customer.name,
                    'sent': False,
                    'error': 'Nimbus SMS not configured',
                }
            )
            continue

        sms_result = send_daily_digest_sms(
            seller=seller,
            customer=customer,
            digest=digest,
        )
        if sms_result.get('sent'):
            digest.sms_sent_at = timezone.now()
            digest.save(update_fields=['sms_sent_at', 'updated_at'])
        results.append(
            {
                'digest_id': str(digest.id),
                'customer': customer.name,
                'phone': customer.phone,
                'sent': sms_result.get('sent'),
                'error': sms_result.get('error', ''),
                'statement_url': statement_link(digest.token),
            }
        )
    return results


def get_digest_transactions(digest):
    return LedgerTransaction.objects.filter(
        customer=digest.seller_customer,
        created_at__date=digest.activity_date,
    ).order_by('created_at')


def get_all_customer_transactions(customer):
    return LedgerTransaction.objects.filter(customer=customer).order_by('-created_at')


def get_customer_lifetime_summary(customer):
    """Lifetime credit, payment, and advance totals for this seller–customer link."""
    totals = LedgerTransaction.objects.filter(customer=customer).aggregate(
        total_credit=Sum(
            'amount',
            filter=Q(transaction_type=LedgerTransaction.TYPE_CREDIT),
        ),
        total_payment=Sum(
            'amount',
            filter=Q(transaction_type=LedgerTransaction.TYPE_PAYMENT),
        ),
        total_advance_deposited=Sum(
            'amount',
            filter=Q(transaction_type=LedgerTransaction.TYPE_ADVANCE_DEPOSIT),
        ),
        total_advance_used=Sum(
            'amount',
            filter=Q(transaction_type=LedgerTransaction.TYPE_ADVANCE_USE),
        ),
    )
    return {
        'total_credit': totals['total_credit'] or Decimal('0'),
        'total_payment': totals['total_payment'] or Decimal('0'),
        'total_advance_deposited': customer.advance_deposited,
        'total_advance_used': customer.advance_used,
        'advance_balance': customer.advance_balance,
        'outstanding': customer.outstanding_amount,
        'transaction_count': LedgerTransaction.objects.filter(customer=customer).count(),
    }
