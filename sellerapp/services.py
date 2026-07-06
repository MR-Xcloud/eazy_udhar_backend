from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from easyudhar.payment_utils import payment_method_label

from .models import LedgerTransaction, SellerCustomer
from .utils import format_inr, format_inr_signed


def _local_dt(dt):
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return timezone.localtime(dt)
    return dt


def _time_label(dt):
    dt = _local_dt(dt)
    if dt is None:
        return '—'
    now = timezone.localtime()
    if dt.date() == now.date():
        return f'Today, {dt.strftime("%I:%M %p")}'
    if dt.date() == (now - timedelta(days=1)).date():
        return f'Yesterday, {dt.strftime("%I:%M %p")}'
    return dt.strftime('%d %b, %I:%M %p')


def advance_summary(source):
    """Build advance payload with all field name aliases the app accepts."""
    deposited = source.advance_deposited
    used = source.advance_used
    remaining = source.advance_balance
    summary = {
        'total_deposited': float(deposited),
        'total_used': float(used),
        'remaining': float(remaining),
        'advance_deposited': float(deposited),
        'advance_used': float(used),
        'advance_balance': float(remaining),
        'deposited': float(deposited),
        'used': float(used),
        'balance_available': float(remaining),
    }
    return summary


def _attach_advance_fields(data, customer):
    summary = advance_summary(customer)
    data['advance'] = summary
    data.update(summary)
    return data


def sync_advance_to_account(customer, account):
    account.advance_deposited = customer.advance_deposited
    account.advance_used = customer.advance_used
    account.save(update_fields=['advance_deposited', 'advance_used', 'updated_at'])


def _customer_due_fields(customer):
    due = customer.next_due_date
    overdue = customer.is_overdue
    return {
        'next_due_date': due.isoformat() if due else None,
        'due_date': due.isoformat() if due else None,
        'due_date_display': due.strftime('%d %b %Y') if due else '',
        'overdue': overdue,
        'is_overdue': overdue,
    }


def _parse_due_date(value):
    if value is None or value == '':
        return None
    if hasattr(value, 'year'):
        return value
    from django.utils.dateparse import parse_date

    parsed = parse_date(str(value))
    if parsed is None:
        raise ValueError('due_date must be YYYY-MM-DD')
    return parsed


def refresh_due_status(customer, *, save=True):
    if customer.outstanding_amount <= 0:
        customer.status = SellerCustomer.STATUS_SETTLED
        customer.outstanding_amount = Decimal('0')
        customer.next_due_date = None
    elif customer.next_due_date and customer.next_due_date < timezone.localdate():
        customer.status = SellerCustomer.STATUS_OVERDUE
    else:
        customer.status = SellerCustomer.STATUS_PENDING
    if save:
        customer.save()
    return customer


def refresh_overdue_for_seller(seller):
    """Mark customers overdue when their due date has passed."""
    today = timezone.localdate()
    now = timezone.now()
    pending = list(
        SellerCustomer.objects.filter(
            seller=seller,
            outstanding_amount__gt=0,
            next_due_date__lt=today,
        ).exclude(status=SellerCustomer.STATUS_OVERDUE)
    )
    for customer in pending:
        customer.status = SellerCustomer.STATUS_OVERDUE
        customer.updated_at = now
    if pending:
        SellerCustomer.objects.bulk_update(pending, ['status', 'updated_at'])

    cleared = list(
        SellerCustomer.objects.filter(
            seller=seller,
            outstanding_amount__gt=0,
            status=SellerCustomer.STATUS_OVERDUE,
        ).filter(
            Q(next_due_date__isnull=True) | Q(next_due_date__gte=today)
        )
    )
    for customer in cleared:
        customer.status = SellerCustomer.STATUS_PENDING
        customer.updated_at = now
    if cleared:
        SellerCustomer.objects.bulk_update(cleared, ['status', 'updated_at'])


def customer_list_item(c, *, latest_tx=None):
    if latest_tx is None:
        prefetched = getattr(c, 'latest_transactions', None)
        if prefetched:
            latest_tx = prefetched[0]
        else:
            latest_tx = c.transactions.first()
    last_at = latest_tx.effective_at if latest_tx else c.updated_at
    outstanding = c.outstanding_amount
    data = {
      'id': str(c.id),
      'client_id': str(c.client_id) if c.client_id else None,
      'name': c.name,
      'phone': c.phone,
      'initials': c.initials,
      'outstanding': float(outstanding),
      'outstanding_display': format_inr(outstanding),
      'last_activity_at': last_at.isoformat(),
      'time_label': _time_label(last_at),
      'amount': format_inr(outstanding),
      'amount_label': 'TO RECEIVE' if outstanding > 0 else 'SETTLED',
      'status': c.status,
      'overdue': c.is_overdue,
      'is_negative': outstanding < 0,
      'updated_at': c.updated_at.isoformat(),
      'device_created_at': c.device_created_at.isoformat() if c.device_created_at else None,
  }
    data.update(_customer_due_fields(c))
    return _attach_advance_fields(data, c)


def customer_detail(c):
    data = {
        'id': str(c.id),
        'client_id': str(c.client_id) if c.client_id else None,
        'name': c.name,
        'phone': c.phone,
        'initials': c.initials,
        'outstanding': float(c.outstanding_amount),
        'outstanding_display': format_inr(c.outstanding_amount),
        'email': c.email,
        'address': c.address,
        'status': c.status,
        'updated_at': c.updated_at.isoformat(),
        'device_created_at': c.device_created_at.isoformat() if c.device_created_at else None,
    }
    data.update(_customer_due_fields(c))
    return _attach_advance_fields(data, c)


def transaction_item(tx):
    type_meta = {
        LedgerTransaction.TYPE_CREDIT: ('Credit Added', True),
        LedgerTransaction.TYPE_PAYMENT: ('Payment Received', False),
        LedgerTransaction.TYPE_ADVANCE_DEPOSIT: ('Advance Deposit', True),
        LedgerTransaction.TYPE_ADVANCE_USE: ('Advance Purchase', False),
    }
    title, is_positive = type_meta.get(tx.transaction_type, ('Transaction', False))
    effective = tx.effective_at
    return {
        'id': str(tx.id),
        'client_id': str(tx.client_id) if tx.client_id else None,
        'customer_id': str(tx.customer_id),
        'type': tx.transaction_type,
        'title': title,
        'subtitle': _time_label(effective),
        'note': tx.note,
        'amount': float(tx.amount),
        'amount_display': format_inr_signed(tx.amount, positive=is_positive),
        'is_positive': is_positive,
        'payment_method': tx.payment_method or '',
        'payment_method_label': payment_method_label(tx.payment_method or ''),
        'created_at': tx.created_at.isoformat(),
        'updated_at': tx.updated_at.isoformat(),
        'device_created_at': tx.device_created_at.isoformat() if tx.device_created_at else None,
        'effective_at': effective.isoformat(),
        'due_date': tx.due_date.isoformat() if tx.due_date else None,
        'due_date_display': tx.due_date.strftime('%d %b %Y') if tx.due_date else '',
    }


def activity_item(c, tx=None):
    tx = tx or c.transactions.first()
    outstanding = c.outstanding_amount
    settled = c.status in (SellerCustomer.STATUS_SETTLED, SellerCustomer.STATUS_PAID)

    amount_label = 'TO RECEIVE' if outstanding > 0 else 'SETTLED'
    display_amount = format_inr(outstanding)
    if tx:
        if tx.transaction_type == LedgerTransaction.TYPE_PAYMENT:
            display_amount = format_inr(tx.amount)
            amount_label = 'RECEIVED'
            settled = outstanding <= 0
        elif tx.transaction_type == LedgerTransaction.TYPE_CREDIT:
            display_amount = format_inr(tx.amount)
            amount_label = 'CREDIT'
            settled = False
        elif tx.transaction_type == LedgerTransaction.TYPE_ADVANCE_DEPOSIT:
            display_amount = format_inr(tx.amount)
            amount_label = 'WALLET'
        elif tx.transaction_type == LedgerTransaction.TYPE_ADVANCE_USE:
            display_amount = format_inr(tx.amount)
            amount_label = 'WALLET USED'

    return {
        'customer_id': str(c.id),
        'name': c.name,
        'phone': c.phone,
        'initials': c.initials,
        'outstanding': float(outstanding),
        'outstanding_display': format_inr(outstanding),
        'time': _time_label(tx.effective_at) if tx else _time_label(c.updated_at),
        'amount': display_amount,
        'amount_label': amount_label,
        'last_transaction_type': tx.transaction_type if tx else None,
        'status': c.status,
        'overdue': c.is_overdue,
        'settled': settled,
    }


def _transaction_effective_date(tx):
    effective = _local_dt(tx.device_created_at or tx.created_at)
    return effective.date()


def dashboard_data(seller):
    from django.db.models.functions import Coalesce, TruncDate

    refresh_overdue_for_seller(seller)
    customers = SellerCustomer.objects.filter(seller=seller)
    net = customers.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')
    total_receive = net
    total_pay = Decimal('0')

    today = timezone.localdate()
    today_collection = (
        LedgerTransaction.objects.filter(
            seller=seller,
            transaction_type=LedgerTransaction.TYPE_PAYMENT,
        )
        .annotate(effective_date=TruncDate(Coalesce('device_created_at', 'created_at')))
        .filter(effective_date=today)
        .aggregate(t=Sum('amount'))['t']
        or Decimal('0')
    )

    overdue_amount = customers.filter(status=SellerCustomer.STATUS_OVERDUE).aggregate(
        t=Sum('outstanding_amount')
    )['t'] or Decimal('0')

    recent = [
        activity_item(tx.customer, tx)
        for tx in LedgerTransaction.objects.filter(seller=seller).select_related('customer')[:5]
    ]

    if len(recent) < 5:
        seen = {item['customer_id'] for item in recent}
        for c in customers:
            if str(c.id) not in seen:
                recent.append(activity_item(c))
                seen.add(str(c.id))
            if len(recent) >= 5:
                break

    return {
        'user_name': seller.full_name or seller.business_name,
        'net_to_receive': float(net),
        'total_receive': float(total_receive),
        'total_pay': float(total_pay),
        'today_collection': float(today_collection),
        'overdue_amount': float(overdue_amount),
        'recent_activity': recent,
    }


def update_customer_status(customer):
    return refresh_due_status(customer)


@transaction.atomic
def add_credit(
    seller,
    customer,
    amount,
    note='',
    send_sms=None,
    *,
    client_id=None,
    device_created_at=None,
    due_date=None,
):
    from customerapp.messaging import (
        ensure_customer_account,
        link_seller_customer,
        notify_customer_event,
    )
    from customerapp.models import CustomerNotification
    from django.conf import settings

    from .daily_sms import queued_sms_result, record_daily_activity

    if send_sms is None:
        send_sms = settings.NIMBUS_SMS_ENABLED

    parsed_due = None
    if due_date is not None:
        parsed_due = _parse_due_date(due_date)

    purchase_total = Decimal(str(amount))
    credit_amount = purchase_total
    wallet_applied = Decimal('0')
    wallet_tx = None

    wallet_available = customer.advance_balance
    if wallet_available > 0 and credit_amount > 0:
        wallet_applied = min(wallet_available, credit_amount)
        if wallet_applied > 0:
            wallet_tx = use_advance(
                seller,
                customer,
                wallet_applied,
                note=note or 'Purchase paid from wallet balance',
                device_created_at=device_created_at,
            )
            credit_amount -= wallet_applied

    tx = None
    if credit_amount > 0:
        customer.outstanding_amount += credit_amount
        update_fields = ['outstanding_amount', 'updated_at']
        if parsed_due:
            customer.next_due_date = parsed_due
            update_fields.append('next_due_date')
        customer.save(update_fields=update_fields)
        tx = LedgerTransaction.objects.create(
            seller=seller,
            customer=customer,
            transaction_type=LedgerTransaction.TYPE_CREDIT,
            amount=credit_amount,
            note=note,
            due_date=parsed_due,
            client_id=client_id,
            device_created_at=device_created_at,
        )
        refresh_due_status(customer)
    elif wallet_tx and client_id and not wallet_tx.client_id:
        wallet_tx.client_id = client_id
        wallet_tx.save(update_fields=['client_id', 'updated_at'])
        tx = wallet_tx

    primary = tx or wallet_tx
    if primary is None:
        raise ValueError('Purchase amount must be greater than zero.')

    customer_user = link_seller_customer(customer)
    if customer_user:
        account = ensure_customer_account(customer, customer_user)
        account.outstanding_amount = customer.outstanding_amount
        sync_advance_to_account(customer, account)
        account.save(update_fields=['outstanding_amount', 'updated_at'])
        if credit_amount > 0:
            notify_customer_event(
                customer_user,
                account,
                notification_type=CustomerNotification.TYPE_CREDIT,
                title=f'Credit added at {seller.business_name}',
                subtitle=note or f'Rs. {credit_amount} added to your account',
                reference_id=str(tx.id),
            )

    if credit_amount > 0:
        from .notifications import notify_seller_credit

        notify_seller_credit(seller, customer, credit_amount, reference_id=str(tx.id))

    sms_result = None
    if send_sms and primary:
        digest = record_daily_activity(customer, primary)
        sms_result = queued_sms_result(digest)
        print(
            f'[EasyUdhar SMS] add_credit — queued for nightly digest '
            f'url={sms_result.get("statement_url")}',
            flush=True,
        )
    else:
        print('[EasyUdhar SMS] add_credit — SMS skipped (send_sms=false)', flush=True)

    return primary, sms_result


def _receive_payment(
    seller,
    customer,
    amount,
    payment_method='cash',
    note='',
    send_sms=None,
    *,
    client_id=None,
    device_created_at=None,
):
    from easyudhar.payment_utils import normalize_seller_payment_method

    payment_method = normalize_seller_payment_method(payment_method)
    from customerapp.messaging import (
        ensure_customer_account,
        link_seller_customer,
        notify_customer_event,
    )
    from customerapp.models import CustomerNotification
    from django.conf import settings

    from .daily_sms import queued_sms_result, record_daily_activity

    if send_sms is None:
        send_sms = settings.NIMBUS_SMS_ENABLED

    pay = Decimal(str(amount))
    outstanding = customer.outstanding_amount
    applied_to_due = min(pay, outstanding)
    wallet_credit = pay - applied_to_due

    customer.outstanding_amount = outstanding - applied_to_due
    update_fields = ['outstanding_amount', 'updated_at']
    if wallet_credit > 0:
        customer.advance_deposited += wallet_credit
        update_fields.append('advance_deposited')
    customer.save(update_fields=update_fields)

    payment_note = note or ''
    if wallet_credit > 0 and not payment_note:
        payment_note = (
            f'Rs. {applied_to_due} to dues, Rs. {wallet_credit} added to wallet'
            if applied_to_due > 0
            else f'Rs. {wallet_credit} added to wallet balance'
        )
    elif wallet_credit > 0 and payment_note:
        payment_note = f'{payment_note} (Rs. {wallet_credit} to wallet)'

    tx = LedgerTransaction.objects.create(
        seller=seller,
        customer=customer,
        transaction_type=LedgerTransaction.TYPE_PAYMENT,
        amount=pay,
        note=payment_note,
        payment_method=payment_method,
        client_id=client_id,
        device_created_at=device_created_at,
    )
    update_customer_status(customer)

    customer_user = link_seller_customer(customer)
    if customer_user:
        account = ensure_customer_account(customer, customer_user)
        account.outstanding_amount = customer.outstanding_amount
        account.has_balance = customer.outstanding_amount > 0
        sync_advance_to_account(customer, account)
        account.save(update_fields=['outstanding_amount', 'has_balance', 'updated_at'])
        notify_customer_event(
            customer_user,
            account,
            notification_type=CustomerNotification.TYPE_PAYMENT,
            title=f'Payment recorded at {seller.business_name}',
            subtitle=payment_note or f'Rs. {pay} received via {payment_method}',
            reference_id=str(tx.id),
        )

    sms_result = None
    if send_sms:
        digest = record_daily_activity(customer, tx)
        sms_result = queued_sms_result(digest)
        print(
            f'[EasyUdhar SMS] receive_payment — queued for nightly digest '
            f'url={sms_result.get("statement_url")}',
            flush=True,
        )
    else:
        print('[EasyUdhar SMS] receive_payment — SMS skipped (send_sms=false)', flush=True)

    return tx, sms_result


@transaction.atomic
def receive_payment(*args, **kwargs):
    return _receive_payment(*args, **kwargs)


def deposit_advance(
    seller,
    customer,
    amount,
    payment_method='upi',
    note='',
    *,
    client_id=None,
    device_created_at=None,
):
    from easyudhar.payment_utils import normalize_seller_payment_method

    payment_method = normalize_seller_payment_method(payment_method)
    from customerapp.messaging import (
        ensure_customer_account,
        link_seller_customer,
        notify_customer_event,
    )
    from customerapp.models import CustomerNotification

    deposit = Decimal(str(amount))
    customer.advance_deposited += deposit
    customer.save(update_fields=['advance_deposited', 'updated_at'])
    tx = LedgerTransaction.objects.create(
        seller=seller,
        customer=customer,
        transaction_type=LedgerTransaction.TYPE_ADVANCE_DEPOSIT,
        amount=deposit,
        note=note,
        payment_method=payment_method,
        client_id=client_id,
        device_created_at=device_created_at,
    )

    customer_user = link_seller_customer(customer)
    if customer_user:
        account = ensure_customer_account(customer, customer_user)
        sync_advance_to_account(customer, account)
        notify_customer_event(
            customer_user,
            account,
            notification_type=CustomerNotification.TYPE_ADVANCE,
            title=f'Advance received at {seller.business_name}',
            subtitle=note or f'Rs. {deposit} added to your advance balance',
            reference_id=str(tx.id),
        )

    return tx


def use_advance(
    seller,
    customer,
    amount,
    note='',
    *,
    client_id=None,
    device_created_at=None,
):
    from customerapp.messaging import (
        ensure_customer_account,
        link_seller_customer,
        notify_customer_event,
    )
    from customerapp.models import CustomerNotification

    use_amount = Decimal(str(amount))
    remaining = customer.advance_balance
    if use_amount > remaining:
        raise ValueError(
            f'Amount exceeds advance balance. Available: Rs. {remaining}, requested: Rs. {use_amount}.'
        )

    customer.advance_used += use_amount
    customer.save(update_fields=['advance_used', 'updated_at'])
    tx = LedgerTransaction.objects.create(
        seller=seller,
        customer=customer,
        transaction_type=LedgerTransaction.TYPE_ADVANCE_USE,
        amount=use_amount,
        note=note,
        client_id=client_id,
        device_created_at=device_created_at,
    )

    customer_user = link_seller_customer(customer)
    if customer_user:
        account = ensure_customer_account(customer, customer_user)
        sync_advance_to_account(customer, account)
        notify_customer_event(
            customer_user,
            account,
            notification_type=CustomerNotification.TYPE_ADVANCE,
            title=f'Advance used at {seller.business_name}',
            subtitle=note or f'Rs. {use_amount} deducted from your advance',
            reference_id=str(tx.id),
        )

    return tx


def customer_statement_report(customer):
    """Full ledger payload for PDF / share (running balance, wallet, totals)."""
    from django.db.models.functions import Coalesce

    txs = LedgerTransaction.objects.filter(customer=customer).order_by(
        Coalesce('device_created_at', 'created_at'),
        'id',
    )

    outstanding_running = Decimal('0')
    total_credit = Decimal('0')
    total_received = Decimal('0')
    enriched = []

    for tx in txs:
        item = transaction_item(tx)
        debit = Decimal('0')
        credit = Decimal('0')

        if tx.transaction_type == LedgerTransaction.TYPE_CREDIT:
            outstanding_running += tx.amount
            total_credit += tx.amount
            debit = tx.amount
        elif tx.transaction_type == LedgerTransaction.TYPE_PAYMENT:
            total_received += tx.amount
            credit = tx.amount
            outstanding_running = max(outstanding_running - tx.amount, Decimal('0'))
        elif tx.transaction_type == LedgerTransaction.TYPE_ADVANCE_DEPOSIT:
            credit = tx.amount
        elif tx.transaction_type == LedgerTransaction.TYPE_ADVANCE_USE:
            debit = tx.amount

        effective = _local_dt(tx.effective_at)
        parts = [item.get('title') or 'Transaction']
        if tx.note:
            parts.append(tx.note)
        if tx.payment_method:
            parts.append(f'via {tx.payment_method}')
        if tx.due_date and tx.transaction_type == LedgerTransaction.TYPE_CREDIT:
            parts.append(f'due {tx.due_date:%d %b %Y}')

        item.update(
            {
                'type_label': tx.get_transaction_type_display(),
                'date_display': effective.strftime('%d %b %Y, %I:%M %p'),
                'description': ' — '.join(parts),
                'debit': float(debit),
                'credit': float(credit),
                'debit_display': format_inr(debit) if debit > 0 else '—',
                'credit_display': format_inr(credit) if credit > 0 else '—',
                'balance_after': float(outstanding_running),
                'balance_display': format_inr(outstanding_running),
            }
        )
        enriched.append(item)

    enriched.reverse()

    wallet = advance_summary(customer)
    data = {
        'report': 'customer_statement',
        'customer': customer.name,
        'customer_name': customer.name,
        'phone': customer.phone,
        'outstanding': float(customer.outstanding_amount),
        'outstanding_display': format_inr(customer.outstanding_amount),
        'wallet_balance': wallet['remaining'],
        'wallet_display': format_inr(wallet['remaining']),
        'advance': wallet,
        'total_credit_given': float(total_credit),
        'total_credit_display': format_inr(total_credit),
        'total_collected': float(total_received),
        'total_collected_display': format_inr(total_received),
        'transaction_count': len(enriched),
        'transactions': enriched,
        'generated_at': timezone.now().isoformat(),
    }
    data.update(_customer_due_fields(customer))
    return data


def reports_overview(seller):
    customers = SellerCustomer.objects.filter(seller=seller)
    outstanding = customers.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    collected = (
        LedgerTransaction.objects.filter(
            seller=seller,
            transaction_type=LedgerTransaction.TYPE_PAYMENT,
            created_at__gte=month_start,
        ).aggregate(t=Sum('amount'))['t']
        or Decimal('0')
    )
    chart = [
        {'label': 'Jan', 'value': 0.45},
        {'label': 'Feb', 'value': 0.60},
        {'label': 'Mar', 'value': 0.55},
        {'label': 'Apr', 'value': 0.70},
        {'label': 'May', 'value': 0.85},
        {'label': 'Jun', 'value': 0.75},
    ]
    return {
        'collected_this_month': float(collected),
        'growth_percent': 18,
        'outstanding_total': float(outstanding),
        'avg_per_day': float(collected / max(timezone.now().day, 1)),
        'chart': chart,
    }
