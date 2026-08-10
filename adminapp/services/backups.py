from decimal import Decimal

from django.db import transaction

from customerapp.models import (
    AccountStatementLine,
    CustomerAccount,
    CustomerDeviceToken,
    CustomerNotification,
    CustomerPayment,
    CustomerSettings,
    PaymentMethod,
    RazorpayPaymentOrder,
)
from sellerapp.models import Seller, SellerCustomer

BACKUP_SCHEMA_VERSION = 1


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _row(instance, fields):
    return {field: _jsonable(getattr(instance, field)) for field in fields}


def build_customer_backup_payload(customer):
    """Snapshot a customer's profile plus their ledger/app data into a JSON-safe dict."""
    accounts = list(customer.accounts.all())
    statement_lines = AccountStatementLine.objects.filter(account_id__in=[a.id for a in accounts])
    settings_obj = CustomerSettings.objects.filter(user=customer).first()

    return {
        'schema_version': BACKUP_SCHEMA_VERSION,
        'customer': {
            'full_name': customer.full_name,
            'email': customer.email,
            'phone': customer.phone,
            'promo_code': customer.promo_code,
            'is_active': customer.is_active,
        },
        'accounts': [
            _row(a, [
                'id', 'shop_name', 'seller_id', 'seller_customer_id',
                'outstanding_amount', 'advance_deposited', 'advance_used',
                'next_due_date', 'status', 'has_balance',
            ])
            for a in accounts
        ],
        'statement_lines': [
            _row(line, ['id', 'account_id', 'description', 'amount', 'line_type', 'date'])
            for line in statement_lines
        ],
        'payments': [
            _row(p, [
                'id', 'account_id', 'amount', 'method', 'status', 'reference_id',
                'razorpay_order_id', 'razorpay_payment_id', 'is_partial',
            ])
            for p in customer.payments.all()
        ],
        'razorpay_orders': [
            _row(o, [
                'id', 'amount', 'currency', 'shop_ids', 'account_id', 'reference_id',
                'razorpay_order_id', 'razorpay_payment_id', 'payment_method', 'status',
                'error_message', 'paid_at',
            ])
            for o in customer.razorpay_orders.all()
        ],
        'payment_methods': [
            _row(m, ['id', 'method_type', 'label', 'upi_id', 'account_ref', 'is_default'])
            for m in customer.payment_methods.all()
        ],
        'notifications': [
            _row(n, [
                'id', 'notification_type', 'title', 'subtitle', 'shop_account_id',
                'reference_id', 'is_read',
            ])
            for n in customer.notifications.all()
        ],
        'device_tokens': [
            _row(d, ['id', 'token', 'platform', 'device_id', 'is_active'])
            for d in customer.device_tokens.all()
        ],
        'settings': (
            _row(settings_obj, [
                'language', 'privacy_show_phone', 'privacy_show_email',
                'keep_signed_in', 'push_notifications_enabled',
            ])
            if settings_obj else None
        ),
    }


def backup_summary(payload):
    return {
        'accounts': len(payload.get('accounts') or []),
        'statement_lines': len(payload.get('statement_lines') or []),
        'payments': len(payload.get('payments') or []),
        'notifications': len(payload.get('notifications') or []),
        'device_tokens': len(payload.get('device_tokens') or []),
    }


@transaction.atomic
def restore_customer_backup(customer, backup):
    """Overwrite a customer's ledger/app data with a previously saved backup.

    Restored rows keep their original ids so cross-references between accounts,
    payments and notifications stay intact; timestamps are not preserved since
    Django regenerates auto_now(_add) fields on insert.
    """
    payload = backup.payload

    profile = payload.get('customer') or {}
    if profile.get('full_name') is not None:
        customer.full_name = profile['full_name']
    if profile.get('phone'):
        customer.phone = profile['phone']
    customer.promo_code = profile.get('promo_code') or ''
    if 'is_active' in profile:
        customer.is_active = profile['is_active']
    customer.save(update_fields=['full_name', 'phone', 'promo_code', 'is_active', 'updated_at'])

    customer.notifications.all().delete()
    customer.device_tokens.all().delete()
    customer.payment_methods.all().delete()
    customer.razorpay_orders.all().delete()
    customer.payments.all().delete()
    customer.accounts.all().delete()  # cascades to statement_lines

    accounts_payload = payload.get('accounts') or []
    valid_seller_ids = set(
        Seller.objects.filter(
            id__in=[a['seller_id'] for a in accounts_payload if a.get('seller_id')]
        ).values_list('id', flat=True)
    )
    valid_seller_customer_ids = set(
        SellerCustomer.objects.filter(
            id__in=[a['seller_customer_id'] for a in accounts_payload if a.get('seller_customer_id')]
        ).values_list('id', flat=True)
    )

    account_ids = set()
    accounts = []
    for a in accounts_payload:
        account_ids.add(a['id'])
        accounts.append(CustomerAccount(
            id=a['id'],
            user=customer,
            shop_name=a['shop_name'],
            seller_id=a['seller_id'] if a.get('seller_id') in valid_seller_ids else None,
            seller_customer_id=(
                a['seller_customer_id'] if a.get('seller_customer_id') in valid_seller_customer_ids else None
            ),
            outstanding_amount=a['outstanding_amount'],
            advance_deposited=a['advance_deposited'],
            advance_used=a['advance_used'],
            next_due_date=a['next_due_date'],
            status=a['status'],
            has_balance=a['has_balance'],
        ))
    CustomerAccount.objects.bulk_create(accounts)

    statement_lines = [
        AccountStatementLine(
            id=line['id'],
            account_id=line['account_id'],
            description=line['description'],
            amount=line['amount'],
            line_type=line['line_type'],
            date=line['date'],
        )
        for line in (payload.get('statement_lines') or [])
        if line['account_id'] in account_ids
    ]
    AccountStatementLine.objects.bulk_create(statement_lines)

    payments = [
        CustomerPayment(
            id=p['id'],
            user=customer,
            account_id=p['account_id'] if p.get('account_id') in account_ids else None,
            amount=p['amount'],
            method=p['method'],
            status=p['status'],
            reference_id=p.get('reference_id', ''),
            razorpay_order_id=p.get('razorpay_order_id', ''),
            razorpay_payment_id=p.get('razorpay_payment_id', ''),
            is_partial=p.get('is_partial', False),
        )
        for p in (payload.get('payments') or [])
    ]
    CustomerPayment.objects.bulk_create(payments)

    orders = [
        RazorpayPaymentOrder(
            id=o['id'],
            user=customer,
            amount=o['amount'],
            currency=o.get('currency', 'INR'),
            shop_ids=o.get('shop_ids', []),
            account_id=o.get('account_id'),
            reference_id=o['reference_id'],
            razorpay_order_id=o['razorpay_order_id'],
            razorpay_payment_id=o.get('razorpay_payment_id', ''),
            payment_method=o.get('payment_method', ''),
            status=o['status'],
            error_message=o.get('error_message', ''),
            paid_at=o.get('paid_at'),
        )
        for o in (payload.get('razorpay_orders') or [])
    ]
    RazorpayPaymentOrder.objects.bulk_create(orders)

    methods = [
        PaymentMethod(
            id=m['id'],
            user=customer,
            method_type=m['method_type'],
            label=m.get('label', ''),
            upi_id=m.get('upi_id', ''),
            account_ref=m.get('account_ref', ''),
            is_default=m.get('is_default', False),
        )
        for m in (payload.get('payment_methods') or [])
    ]
    PaymentMethod.objects.bulk_create(methods)

    notifications = [
        CustomerNotification(
            id=n['id'],
            user=customer,
            notification_type=n['notification_type'],
            title=n['title'],
            subtitle=n.get('subtitle', ''),
            shop_account_id=n['shop_account_id'] if n.get('shop_account_id') in account_ids else None,
            reference_id=n.get('reference_id', ''),
            is_read=n.get('is_read', False),
        )
        for n in (payload.get('notifications') or [])
    ]
    CustomerNotification.objects.bulk_create(notifications)

    devices = [
        CustomerDeviceToken(
            id=d['id'],
            user=customer,
            token=d['token'],
            platform=d['platform'],
            device_id=d.get('device_id', ''),
            is_active=d.get('is_active', True),
        )
        for d in (payload.get('device_tokens') or [])
    ]
    CustomerDeviceToken.objects.bulk_create(devices)

    settings_payload = payload.get('settings')
    if settings_payload:
        CustomerSettings.objects.update_or_create(user=customer, defaults=settings_payload)
