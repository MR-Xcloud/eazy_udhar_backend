from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import LedgerTransaction, SellerCustomer
from .utils import format_inr, format_inr_signed


def _time_label(dt):
    now = timezone.now()
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


def customer_list_item(c):
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
        'created_at': tx.created_at.isoformat(),
        'updated_at': tx.updated_at.isoformat(),
        'device_created_at': tx.device_created_at.isoformat() if tx.device_created_at else None,
        'effective_at': effective.isoformat(),
    }


def activity_item(c, tx=None):
    tx = tx or c.transactions.first()
    outstanding = c.outstanding_amount
    settled = c.status in (SellerCustomer.STATUS_SETTLED, SellerCustomer.STATUS_PAID)
    return {
        'customer_id': str(c.id),
        'name': c.name,
        'phone': c.phone,
        'initials': c.initials,
        'outstanding': float(outstanding),
        'outstanding_display': format_inr(outstanding),
        'time': _time_label(tx.effective_at) if tx else _time_label(c.updated_at),
        'amount': format_inr(outstanding),
        'status': c.status,
        'overdue': c.is_overdue,
        'settled': settled,
    }


def _transaction_effective_date(tx):
    return (tx.device_created_at or tx.created_at).date()


def dashboard_data(seller):
    customers = SellerCustomer.objects.filter(seller=seller)
    net = customers.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')
    total_receive = net
    total_pay = Decimal('0')

    today = timezone.localdate()
    today_collection = Decimal('0')
    for tx in LedgerTransaction.objects.filter(
        seller=seller,
        transaction_type=LedgerTransaction.TYPE_PAYMENT,
    ).only('amount', 'created_at', 'device_created_at'):
        if _transaction_effective_date(tx) == today:
            today_collection += tx.amount

    overdue_amount = customers.filter(status=SellerCustomer.STATUS_OVERDUE).aggregate(
        t=Sum('outstanding_amount')
    )['t'] or Decimal('0')

    recent = []
    seen = set()
    for tx in LedgerTransaction.objects.filter(seller=seller).select_related('customer')[:10]:
        if tx.customer_id in seen:
            continue
        seen.add(tx.customer_id)
        recent.append(activity_item(tx.customer, tx))
        if len(recent) >= 5:
            break

    if len(recent) < 5:
        for c in customers[: 5 - len(recent)]:
            if c.id not in seen:
                recent.append(activity_item(c))

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
    if customer.outstanding_amount <= 0:
        customer.status = SellerCustomer.STATUS_SETTLED
        customer.outstanding_amount = Decimal('0')
    elif customer.is_overdue:
        customer.status = SellerCustomer.STATUS_OVERDUE
    else:
        customer.status = SellerCustomer.STATUS_PENDING
    customer.save()


def add_credit(
    seller,
    customer,
    amount,
    note='',
    send_sms=None,
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
    from django.conf import settings

    from .daily_sms import queued_sms_result, record_daily_activity

    if send_sms is None:
        send_sms = settings.NIMBUS_SMS_ENABLED

    customer.outstanding_amount += Decimal(str(amount))
    customer.save()
    tx = LedgerTransaction.objects.create(
        seller=seller,
        customer=customer,
        transaction_type=LedgerTransaction.TYPE_CREDIT,
        amount=amount,
        note=note,
        client_id=client_id,
        device_created_at=device_created_at,
    )
    update_customer_status(customer)

    customer_user = link_seller_customer(customer)
    if customer_user:
        account = ensure_customer_account(customer, customer_user)
        account.outstanding_amount = customer.outstanding_amount
        account.save(update_fields=['outstanding_amount'])
        notify_customer_event(
            customer_user,
            account,
            notification_type=CustomerNotification.TYPE_CREDIT,
            title=f'Credit added at {seller.business_name}',
            subtitle=note or f'Rs. {amount} added to your account',
            reference_id=str(tx.id),
        )

    from .notifications import notify_seller_credit

    notify_seller_credit(seller, customer, amount, reference_id=str(tx.id))

    sms_result = None
    if send_sms:
        digest = record_daily_activity(customer, tx)
        sms_result = queued_sms_result(digest)
        print(
            f'[EasyUdhar SMS] add_credit — queued for nightly digest '
            f'url={sms_result.get("statement_url")}',
            flush=True,
        )
    else:
        print('[EasyUdhar SMS] add_credit — SMS skipped (send_sms=false)', flush=True)

    return tx, sms_result


def receive_payment(
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
    customer.outstanding_amount = max(customer.outstanding_amount - pay, Decimal('0'))
    customer.save()
    tx = LedgerTransaction.objects.create(
        seller=seller,
        customer=customer,
        transaction_type=LedgerTransaction.TYPE_PAYMENT,
        amount=pay,
        note=note,
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
        account.save(update_fields=['outstanding_amount', 'has_balance', 'updated_at'])
        notify_customer_event(
            customer_user,
            account,
            notification_type=CustomerNotification.TYPE_PAYMENT,
            title=f'Payment recorded at {seller.business_name}',
            subtitle=note or f'Rs. {pay} received via {payment_method}',
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


def deposit_advance(
    seller,
    customer,
    amount,
    payment_method='UPI',
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
