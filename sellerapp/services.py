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


def customer_list_item(c):
    latest_tx = c.transactions.first()
    last_at = latest_tx.created_at if latest_tx else c.updated_at
    outstanding = c.outstanding_amount
    return {
      'id': str(c.id),
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
  }


def customer_detail(c):
    return {
        'id': str(c.id),
        'name': c.name,
        'phone': c.phone,
        'initials': c.initials,
        'outstanding': float(c.outstanding_amount),
        'outstanding_display': format_inr(c.outstanding_amount),
        'email': c.email,
        'address': c.address,
        'status': c.status,
    }


def transaction_item(tx):
    is_positive = tx.transaction_type == LedgerTransaction.TYPE_CREDIT
    return {
        'id': str(tx.id),
        'type': tx.transaction_type,
        'title': 'Credit Added' if is_positive else 'Payment Received',
        'subtitle': _time_label(tx.created_at),
        'note': tx.note,
        'amount': float(tx.amount),
        'amount_display': format_inr_signed(tx.amount, positive=is_positive),
        'is_positive': is_positive,
        'payment_method': tx.payment_method or '',
        'created_at': tx.created_at.isoformat(),
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
        'time': _time_label(tx.created_at) if tx else _time_label(c.updated_at),
        'amount': format_inr(outstanding),
        'status': c.status,
        'overdue': c.is_overdue,
        'settled': settled,
    }


def dashboard_data(seller):
    customers = SellerCustomer.objects.filter(seller=seller)
    net = customers.aggregate(t=Sum('outstanding_amount'))['t'] or Decimal('0')
    total_receive = net
    total_pay = Decimal('0')

    today = timezone.now().date()
    today_collection = (
        LedgerTransaction.objects.filter(
            seller=seller,
            transaction_type=LedgerTransaction.TYPE_PAYMENT,
            created_at__date=today,
        ).aggregate(t=Sum('amount'))['t']
        or Decimal('0')
    )

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


def add_credit(seller, customer, amount, note='', send_sms=None):
    from customerapp.messaging import (
        ensure_customer_account,
        link_seller_customer,
        notify_customer_event,
    )
    from customerapp.models import CustomerNotification
    from django.conf import settings

    from .nimbus_sms import nimbus_sms_configured, send_credit_sms

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

    sms_result = None
    if send_sms and nimbus_sms_configured():
        print('[EasyUdhar SMS] add_credit — attempting SMS...', flush=True)
        sms_result = send_credit_sms(
            seller=seller,
            customer=customer,
            amount=amount,
            balance=customer.outstanding_amount,
        )
        print(
            f'[EasyUdhar SMS] add_credit — done sent={sms_result.get("sent")} '
            f'error={sms_result.get("error")!r}',
            flush=True,
        )
    elif send_sms and not nimbus_sms_configured():
        print('[EasyUdhar SMS] add_credit — SMS disabled (Nimbus not configured)', flush=True)
        sms_result = {
            'sent': False,
            'message_id': '',
            'error': 'Nimbus SMS not configured (set NIMBUS_DLT_ENTITY_ID).',
            'raw_response': '',
        }
    elif not send_sms:
        print('[EasyUdhar SMS] add_credit — SMS skipped (send_sms=false)', flush=True)

    return tx, sms_result


def receive_payment(seller, customer, amount, payment_method='cash', note='', send_sms=None):
    from customerapp.messaging import (
        ensure_customer_account,
        link_seller_customer,
        notify_customer_event,
    )
    from customerapp.models import CustomerNotification
    from django.conf import settings

    from .nimbus_sms import nimbus_sms_configured, send_payment_sms

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
    )
    update_customer_status(customer)

    customer_user = link_seller_customer(customer)
    if customer_user:
        account = ensure_customer_account(customer, customer_user)
        account.outstanding_amount = customer.outstanding_amount
        account.has_balance = customer.outstanding_amount > 0
        account.save(update_fields=['outstanding_amount', 'has_balance'])
        notify_customer_event(
            customer_user,
            account,
            notification_type=CustomerNotification.TYPE_PAYMENT,
            title=f'Payment recorded at {seller.business_name}',
            subtitle=note or f'Rs. {pay} received via {payment_method}',
            reference_id=str(tx.id),
        )

    sms_result = None
    if send_sms and nimbus_sms_configured():
        print('[EasyUdhar SMS] receive_payment — attempting SMS...', flush=True)
        sms_result = send_payment_sms(
            seller=seller,
            customer=customer,
            amount=pay,
            balance=customer.outstanding_amount,
            payment_method=payment_method,
        )
        print(
            f'[EasyUdhar SMS] receive_payment — done sent={sms_result.get("sent")} '
            f'error={sms_result.get("error")!r}',
            flush=True,
        )
    elif send_sms and not nimbus_sms_configured():
        print('[EasyUdhar SMS] receive_payment — SMS disabled (Nimbus not configured)', flush=True)
        sms_result = {
            'sent': False,
            'message_id': '',
            'error': 'Nimbus SMS not configured (set NIMBUS_DLT_ENTITY_ID).',
            'raw_response': '',
        }
    elif not send_sms:
        print('[EasyUdhar SMS] receive_payment — SMS skipped (send_sms=false)', flush=True)

    return tx, sms_result


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
