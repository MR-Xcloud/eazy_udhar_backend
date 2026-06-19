import secrets
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone

from customerapp.messaging import normalize_phone

from .models import CustomerDayDigest, CustomerNightlyDigest, LedgerTransaction


def statement_link(token):
    base = settings.PUBLIC_STATEMENT_BASE_URL.rstrip('/')
    return f'{base}/{token}'


def merged_shop_label(digests):
    """Short shop label for merged nightly SMS (DLT var max ~30 chars)."""
    names = []
    seen = set()
    for digest in digests:
        name = (digest.seller_customer.seller.business_name or '').strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    if not names:
        return getattr(settings, 'NIMBUS_SMS_PLATFORM_NAME', 'EAZYUDHAR')
    if len(names) == 1:
        label = names[0]
    elif len(names) == 2:
        label = f'{names[0]}, {names[1]}'
    else:
        label = f'{names[0]} +{len(names) - 1} shops'

    max_len = getattr(settings, 'NIMBUS_SMS_VAR_MAX_LENGTH', 30)
    if max_len > 0 and len(label) > max_len:
        return label[:max_len]
    return label


def ensure_statement_digest(customer, activity_date=None):
    """Return today's digest row so reminder SMS can include a statement link."""
    if activity_date is None:
        activity_date = timezone.localdate()
    digest, _ = CustomerDayDigest.objects.get_or_create(
        seller_customer=customer,
        activity_date=activity_date,
        defaults={'token': secrets.token_urlsafe(16)},
    )
    return digest


def ensure_nightly_digest(phone, activity_date=None):
    """Merged digest token for all shops on this phone for the given date."""
    if activity_date is None:
        activity_date = timezone.localdate()
    nightly, _ = CustomerNightlyDigest.objects.get_or_create(
        phone=phone,
        activity_date=activity_date,
        defaults={'token': secrets.token_urlsafe(16)},
    )
    return nightly


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
    phone = normalize_phone(digest.seller_customer.phone)
    nightly = ensure_nightly_digest(phone) if phone else None
    link_token = nightly.token if nightly else digest.token
    return {
        'sent': False,
        'queued': True,
        'message': 'SMS queued for nightly digest',
        'digest_token': link_token,
        'statement_url': statement_link(link_token),
        'message_id': '',
        'error': '',
        'raw_response': '',
    }


def digests_for_phone(activity_date, phone):
    """All shop digests for one customer phone on a given date."""
    matched = []
    qs = CustomerDayDigest.objects.filter(
        activity_date=activity_date,
        transaction_count__gt=0,
    ).select_related('seller_customer', 'seller_customer__seller')
    for digest in qs:
        if normalize_phone(digest.seller_customer.phone) == phone:
            matched.append(digest)
    return matched


def _group_pending_digests(qs):
    groups = defaultdict(list)
    for digest in qs:
        phone = normalize_phone(digest.seller_customer.phone)
        if phone:
            groups[phone].append(digest)
    return groups


def send_pending_digests(*, activity_date=None, force=False):
    """
    Send one merged digest SMS per customer phone for the given activity date.
    A customer with activity at multiple shops gets a single SMS at night.
    """
    from .nimbus_sms import nimbus_sms_configured, send_merged_nightly_digest_sms

    if activity_date is None:
        activity_date = timezone.localdate()

    qs = CustomerDayDigest.objects.filter(
        activity_date=activity_date,
        transaction_count__gt=0,
    ).select_related('seller_customer', 'seller_customer__seller')
    if not force:
        qs = qs.filter(sms_sent_at__isnull=True)

    results = []
    for phone, digests in _group_pending_digests(qs).items():
        nightly = ensure_nightly_digest(phone, activity_date)
        if not force and nightly.sms_sent_at:
            now = nightly.sms_sent_at
            for digest in digests:
                if digest.sms_sent_at is None:
                    digest.sms_sent_at = now
                    digest.save(update_fields=['sms_sent_at', 'updated_at'])
            results.append(
                {
                    'phone': phone,
                    'customer': digests[0].seller_customer.name,
                    'shops': len(digests),
                    'sent': True,
                    'error': '',
                    'statement_url': statement_link(nightly.token),
                    'skipped': True,
                }
            )
            continue

        credit_total = sum((d.credit_total for d in digests), Decimal('0'))
        payment_total = sum((d.payment_total for d in digests), Decimal('0'))

        if not nimbus_sms_configured():
            results.append(
                {
                    'phone': phone,
                    'customer': digests[0].seller_customer.name,
                    'shops': len(digests),
                    'sent': False,
                    'error': 'Nimbus SMS not configured',
                }
            )
            continue

        sms_result = send_merged_nightly_digest_sms(
            phone=phone,
            digests=digests,
            nightly=nightly,
            credit_total=credit_total,
            payment_total=payment_total,
        )
        if sms_result.get('sent'):
            sent_at = timezone.now()
            nightly.sms_sent_at = sent_at
            nightly.save(update_fields=['sms_sent_at', 'updated_at'])
            for digest in digests:
                digest.sms_sent_at = sent_at
                digest.save(update_fields=['sms_sent_at', 'updated_at'])

        results.append(
            {
                'phone': phone,
                'customer': digests[0].seller_customer.name,
                'shops': len(digests),
                'sent': sms_result.get('sent'),
                'error': sms_result.get('error', ''),
                'statement_url': statement_link(nightly.token),
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
