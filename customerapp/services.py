import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from easyudhar.payment_utils import normalize_payment_method, payment_method_label

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


def _account_seller_upi(account):
    seller = account.seller
    if seller is None and account.seller_customer_id:
        seller = getattr(account.seller_customer, 'seller', None)
    if seller is None:
        return ''
    return (seller.upi_id or '').strip()


def payment_summary(user):
    accounts = CustomerAccount.objects.filter(user=user, has_balance=True).select_related(
        'seller', 'seller_customer__seller'
    )
    total_due = accounts.aggregate(total=Sum('outstanding_amount'))['total'] or Decimal('0')
    splits = [
        {
            'shop_id': str(a.id),
            'shop_name': a.shop_name,
            'amount': str(a.outstanding_amount),
            'outstanding_amount': str(a.outstanding_amount),
            'seller_upi_id': _account_seller_upi(a),
        }
        for a in accounts
    ]
    return {
        'total_due': str(total_due),
        'total': str(total_due),
        'total_amount': str(total_due),
        'total_to_pay': str(total_due),
        'partial_payment_allowed': True,
        'shops': splits,
        'splits': splits,
        'accounts': splits,
    }


def payment_history(user, *, page=1, page_size=25, shop_id=None, method=None):
    qs = CustomerPayment.objects.filter(user=user).select_related('account').order_by('-created_at')
    if shop_id:
        qs = qs.filter(account_id=shop_id)
    if method:
        qs = qs.filter(method=normalize_payment_method(method))
    total = qs.count()
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 25), 1), 100)
    start = (page - 1) * page_size
    rows = qs[start : start + page_size]
    return {
        'data': [_payment_history_item(p) for p in rows],
        'meta': {'page': page, 'page_size': page_size, 'total': total},
    }


def _payment_history_item(payment):
    account = payment.account
    return {
        'id': str(payment.id),
        'shop_id': str(account.id) if account else None,
        'shop_name': account.shop_name if account else None,
        'amount': str(payment.amount),
        'method': payment.method,
        'method_label': payment_method_label(payment.method),
        'status': payment.status,
        'is_partial': payment.is_partial,
        'reference_id': payment.reference_id,
        'razorpay_order_id': payment.razorpay_order_id or None,
        'razorpay_payment_id': payment.razorpay_payment_id or None,
        'created_at': payment.created_at.isoformat(),
    }


@transaction.atomic
def process_payment(
    user,
    shop_ids,
    amount,
    method,
    account=None,
    *,
    reference_id=None,
    razorpay_order_id='',
    razorpay_payment_id='',
):
    if not reference_id:
        reference_id = f'PAY-{uuid.uuid4().hex[:12].upper()}'
    remaining = Decimal(str(amount))
    method = normalize_payment_method(method)

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
        outstanding_before = acc.outstanding_amount
        pay_amount = min(remaining, outstanding_before)
        if pay_amount <= 0:
            continue
        is_partial = pay_amount < outstanding_before
        payment = CustomerPayment.objects.create(
            user=user,
            account=acc,
            amount=pay_amount,
            method=method,
            status=CustomerPayment.STATUS_SUCCESS,
            reference_id=reference_id,
            razorpay_order_id=razorpay_order_id or '',
            razorpay_payment_id=razorpay_payment_id or '',
            is_partial=is_partial,
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
            from sellerapp.models import LedgerTransaction, SellerCustomer
            from sellerapp.notifications import notify_seller_payment
            from sellerapp.services import update_customer_status

            sc = acc.seller_customer
            sc.outstanding_amount = max(sc.outstanding_amount - pay_amount, Decimal('0'))
            if sc.outstanding_amount <= 0:
                sc.status = SellerCustomer.STATUS_SETTLED
            sc.save(update_fields=['outstanding_amount', 'status', 'updated_at'])
            LedgerTransaction.objects.create(
                seller=sc.seller,
                customer=sc,
                transaction_type=LedgerTransaction.TYPE_PAYMENT,
                amount=pay_amount,
                note=f'Customer app payment ({reference_id})',
                payment_method=method,
            )
            update_customer_status(sc)
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

    if remaining > 0 and account and len(targets) == 1 and account.seller_customer_id:
        from sellerapp.services import deposit_advance

        sc = account.seller_customer
        deposit_advance(
            sc.seller,
            sc,
            remaining,
            payment_method=method,
            note=f'Wallet top-up from customer app ({reference_id})',
        )
        remaining = Decimal('0')

    return payments, reference_id
