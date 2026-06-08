import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    AccountStatementLine,
    CustomerAccount,
    CustomerNotification,
    CustomerPayment,
)


def dashboard_summary(user):
    accounts = CustomerAccount.objects.filter(user=user, has_balance=True)
    all_accounts = CustomerAccount.objects.filter(user=user)
    total_outstanding = accounts.aggregate(total=Sum('outstanding_amount'))['total'] or Decimal('0')
    total_advance_remaining = sum(
        (a.advance_balance for a in all_accounts),
        Decimal('0'),
    )
    shop_count = accounts.count()
    overdue_accounts = [a for a in accounts if a.is_overdue]
    pay_now_amount = sum((a.outstanding_amount for a in overdue_accounts), Decimal('0'))
    if pay_now_amount == 0 and total_outstanding > 0:
        pay_now_amount = total_outstanding
    return {
        'name': user.full_name or user.email,
        'total_outstanding': str(total_outstanding),
        'total_advance_remaining': str(total_advance_remaining),
        'shop_count': shop_count,
        'pay_now_amount': str(pay_now_amount),
    }


def payment_summary(user):
    accounts = CustomerAccount.objects.filter(user=user, has_balance=True)
    total_due = accounts.aggregate(total=Sum('outstanding_amount'))['total'] or Decimal('0')
    splits = [
        {
            'shop_id': str(a.id),
            'shop_name': a.shop_name,
            'amount': str(a.outstanding_amount),
        }
        for a in accounts
    ]
    return {'total_due': str(total_due), 'shops': splits}


@transaction.atomic
def process_payment(user, shop_ids, amount, method, account=None):
    reference_id = f'PAY-{uuid.uuid4().hex[:12].upper()}'
    remaining = Decimal(str(amount))

    if account:
        targets = [account]
    else:
        targets = list(
            CustomerAccount.objects.filter(user=user, id__in=shop_ids, has_balance=True)
        )

    if not targets:
        raise ValueError('No valid shop accounts found for payment.')

    payments = []
    for acc in targets:
        if remaining <= 0:
            break
        pay_amount = min(remaining, acc.outstanding_amount)
        if pay_amount <= 0:
            continue
        payment = CustomerPayment.objects.create(
            user=user,
            account=acc,
            amount=pay_amount,
            method=method,
            status=CustomerPayment.STATUS_SUCCESS,
            reference_id=reference_id,
        )
        acc.outstanding_amount -= pay_amount
        if acc.outstanding_amount <= 0:
            acc.outstanding_amount = Decimal('0')
            acc.has_balance = False
            acc.status = CustomerAccount.STATUS_CLEARED
        remaining -= pay_amount
        acc.save()
        AccountStatementLine.objects.create(
            account=acc,
            description=f'Payment via {method}',
            amount=pay_amount,
            line_type=AccountStatementLine.TYPE_PAYMENT,
            date=timezone.now().date(),
        )
        payments.append(payment)

        if acc.seller_customer_id:
            from sellerapp.models import SellerCustomer
            from sellerapp.notifications import notify_seller_payment

            sc = acc.seller_customer
            sc.outstanding_amount = max(sc.outstanding_amount - pay_amount, Decimal('0'))
            if sc.outstanding_amount <= 0:
                sc.status = SellerCustomer.STATUS_SETTLED
            sc.save(update_fields=['outstanding_amount', 'status', 'updated_at'])
            notify_seller_payment(
                sc.seller,
                sc,
                pay_amount,
                method,
                reference_id=reference_id,
            )

        notification = CustomerNotification.objects.create(
            user=user,
            notification_type=CustomerNotification.TYPE_PAYMENT,
            title='Payment successful',
            subtitle=f'Paid Rs.{pay_amount} via {method}',
            shop_account=acc,
            reference_id=reference_id,
            is_read=False,
        )
        from easyudhar.fcm import push_customer_notification

        push_customer_notification(notification)
    return payments, reference_id
