"""Serialize existing seller/customer models for admin API responses."""

from django.db.models import Count, Sum
from django.utils import timezone

from customerapp.models import (
    Customer,
    CustomerAccount,
    CustomerDeviceToken,
    CustomerNotification,
    CustomerPayment,
    ShopMessage,
)
from sellerapp.models import (
    LedgerTransaction,
    ReminderLog,
    Seller,
    SellerCustomer,
    SellerDeviceToken,
    SellerNotification,
    SellerSettings,
    TeamMember,
)

from adminapp.models import SellerSubscription
from sellerapp.subscription_service import message_quota_dict


def _seller_status(seller):
    return 'suspended' if not seller.is_active else 'active'


def _customer_status(customer):
    return 'suspended' if not customer.is_active else 'active'


def seller_subscription_status(seller):
    sub = (
        SellerSubscription.objects.filter(seller=seller)
        .order_by('-created_at')
        .select_related('plan')
        .first()
    )
    return sub.status if sub else None


def seller_list_item(seller):
    agg = SellerCustomer.objects.filter(seller=seller).aggregate(
        customers_count=Count('id'),
        outstanding_total=Sum('outstanding_amount'),
    )
    quota = message_quota_dict(seller)
    return {
        'id': seller.id,
        'business_name': seller.business_name,
        'full_name': seller.full_name or '',
        'email': seller.email,
        'phone': seller.phone,
        'gst_number': seller.gst_number or None,
        'customers_count': agg['customers_count'] or 0,
        'outstanding_total': float(agg['outstanding_total'] or 0),
        'status': _seller_status(seller),
        'subscription_status': seller_subscription_status(seller),
        'messages_used': quota['messages_used'],
        'message_limit': quota['message_limit'],
        'messages_remaining': quota['messages_remaining'],
        'sms_pack_balance': quota['sms_pack_balance'],
        'created_at': seller.created_at.isoformat(),
        'last_login_at': seller.last_login.isoformat() if seller.last_login else None,
        **_seller_payout_fields(seller),
        **signup_location_fields(seller),
    }


def signup_location_fields(user):
    """Where the account signed up from — same shape for sellers and customers."""
    return {
        'signup_location': user.signup_location or None,
        'signup_city': user.signup_city or None,
        'signup_region': user.signup_region or None,
        'signup_country': user.signup_country or None,
        'signup_ip': user.signup_ip or None,
        'signup_location_source': user.signup_source or None,
    }


def _seller_payout_fields(seller):
    acct = (seller.bank_account_number or '').strip()
    if len(acct) >= 4:
        masked = f'****{acct[-4:]}'
    elif acct:
        masked = '****'
    else:
        masked = ''
    holder = (seller.bank_account_holder or '').strip()
    ifsc = (seller.bank_ifsc or '').strip()
    return {
        'upi_id': seller.upi_id or '',
        'bank_account_holder': holder,
        'bank_account_number': acct,
        'bank_account_number_masked': masked,
        'bank_ifsc': ifsc,
        'razorpay_linked_account_id': seller.razorpay_linked_account_id or '',
        'razorpay_route_status': seller.razorpay_route_status or '',
        'payout_configured': bool(holder and acct and ifsc),
    }


def seller_detail(seller):
    data = seller_list_item(seller)
    overdue_qs = SellerCustomer.objects.filter(
        seller=seller, status=SellerCustomer.STATUS_OVERDUE
    )
    data.update(
        {
            'address': seller.address,
            'city': '',
            'state': '',
            'pincode': '',
            'business_type': '',
            'overdue_count': overdue_qs.count(),
            'overdue_amount': float(
                overdue_qs.aggregate(t=Sum('outstanding_amount'))['t'] or 0
            ),
            **_seller_payout_fields(seller),
        }
    )
    return data


def seller_settings_dict(seller):
    settings, _ = SellerSettings.objects.get_or_create(seller=seller)
    return {
        'reminder_channels': settings.reminder_channels or [],
        'auto_remind_enabled': settings.auto_remind_enabled,
        'auto_remind_days_before': settings.auto_remind_days_before,
        'auto_remind_time': settings.auto_remind_time,
        'daily_summary_enabled': settings.daily_summary_enabled,
        'daily_summary_time': settings.daily_summary_time,
        'daily_summary_channels': settings.daily_summary_channels or [],
        'push_enabled': settings.push_notifications_enabled,
        'push_notifications_enabled': settings.push_notifications_enabled,
        'eod_excel_backup_enabled': settings.eod_excel_backup_enabled,
        'eod_excel_backup_time': settings.eod_excel_backup_time,
        'language': settings.language,
    }


def seller_customer_item(sc):
    last_tx = sc.transactions.order_by('-created_at').first()
    status_map = {
        SellerCustomer.STATUS_OVERDUE: 'overdue',
        SellerCustomer.STATUS_SETTLED: 'settled',
        SellerCustomer.STATUS_PAID: 'settled',
        SellerCustomer.STATUS_PENDING: 'active',
    }
    return {
        'id': str(sc.id),
        'seller_id': sc.seller_id,
        'seller_name': sc.seller.business_name,
        'name': sc.name,
        'phone': sc.phone,
        'email': sc.email or '',
        'outstanding': float(sc.outstanding_amount),
        'status': status_map.get(sc.status, sc.status),
        'last_transaction_at': (
            last_tx.effective_at.isoformat() if last_tx else None
        ),
        'created_at': sc.created_at.isoformat(),
        'updated_at': sc.updated_at.isoformat(),
    }


def seller_customer_detail(sc):
    data = seller_customer_item(sc)
    data.update(
        {
            'address': sc.address or '',
            'city': sc.city or '',
            'state': sc.state or '',
            'country': sc.country or '',
            'next_due_date': sc.next_due_date.isoformat() if sc.next_due_date else None,
            'advance_deposited': float(sc.advance_deposited),
            'advance_used': float(sc.advance_used),
            'advance_balance': float(sc.advance_balance),
            'linked_customer_id': sc.linked_customer_id,
            'client_id': str(sc.client_id) if sc.client_id else None,
            'device_created_at': (
                sc.device_created_at.isoformat() if sc.device_created_at else None
            ),
        }
    )
    return data


def customer_account_detail(account):
    data = customer_account_item(account)
    data.update(
        {
            'customer_email': account.user.email,
            'customer_phone': account.user.phone,
            'advance_deposited': float(account.advance_deposited),
            'advance_used': float(account.advance_used),
            'next_due_date': (
                account.next_due_date.isoformat() if account.next_due_date else None
            ),
            'seller_customer_id': (
                str(account.seller_customer_id) if account.seller_customer_id else None
            ),
            'updated_at': account.updated_at.isoformat(),
        }
    )
    return data


def customer_list_item(customer):
    return {
        'id': customer.id,
        'full_name': customer.full_name or customer.username,
        'email': customer.email,
        'phone': customer.phone,
        'promo_code': customer.promo_code or None,
        'linked_shops': customer.accounts.count(),
        'status': _customer_status(customer),
        'created_at': customer.created_at.isoformat(),
        **signup_location_fields(customer),
    }


def customer_detail(customer):
    data = customer_list_item(customer)
    data['username'] = customer.username
    data['updated_at'] = customer.updated_at.isoformat()
    return data


def customer_account_item(account):
    return {
        'id': str(account.id),
        'customer_id': account.user_id,
        'customer_name': account.user.full_name or account.user.email,
        'seller_id': account.seller_id,
        'seller_name': account.shop_name,
        'outstanding': float(account.outstanding_amount),
        'credit_limit': None,
        'status': account.status,
        'linked_at': account.created_at.isoformat(),
    }


def team_member_item(member):
    return {
        'id': str(member.id),
        'seller_id': member.seller_id,
        'seller_name': member.seller.business_name,
        'name': member.name,
        'email': '',
        'phone': member.phone,
        'role': member.role if member.role in ('owner', 'staff') else 'staff',
        'status': 'active' if member.is_active else 'inactive',
        'created_at': member.created_at.isoformat(),
    }


def ledger_transaction_item(tx):
    from easyudhar.payment_utils import normalize_payment_method, payment_method_label

    source = 'offline_sync' if tx.client_id else 'app'
    method = normalize_payment_method(tx.payment_method or '')
    return {
        'id': str(tx.id),
        'seller_id': tx.seller_id,
        'seller_customer_id': str(tx.customer_id),
        'customer_name': tx.customer.name,
        'type': tx.transaction_type,
        'amount': float(tx.amount),
        'balance_after': float(tx.customer.outstanding_amount),
        'note': tx.note,
        'payment_method': method or None,
        'payment_method_label': payment_method_label(method) if method else None,
        'created_by': tx.seller.business_name,
        'created_at': tx.effective_at.isoformat(),
        'source': source,
    }


def customer_payment_item(payment):
    from easyudhar.payment_utils import normalize_payment_method, payment_method_label

    seller_id = None
    seller_customer_id = None
    if payment.account:
        seller_id = payment.account.seller_id
        if payment.account.seller_customer_id:
            seller_customer_id = str(payment.account.seller_customer_id)
    method = normalize_payment_method(payment.method or 'other')
    return {
        'id': str(payment.id),
        'customer_id': payment.user_id,
        'seller_id': seller_id,
        'seller_customer_id': seller_customer_id,
        'amount': float(payment.amount),
        'method': method,
        'method_label': payment_method_label(method),
        'is_partial': getattr(payment, 'is_partial', False),
        'status': payment.status,
        'reference': payment.reference_id,
        'reference_id': payment.reference_id,
        'razorpay_order_id': payment.razorpay_order_id or None,
        'razorpay_payment_id': payment.razorpay_payment_id or None,
        'created_at': payment.created_at.isoformat(),
    }


def customer_razorpay_order_item(order):
    from easyudhar.payment_utils import payment_method_label

    return {
        'id': str(order.id),
        'source': 'customer_app',
        'customer_id': order.user_id,
        'customer_name': order.user.full_name or order.user.email,
        'seller_id': None,
        'seller_name': None,
        'customer_name_on_ledger': None,
        'amount': float(order.amount),
        'currency': order.currency,
        'status': order.status,
        'reference_id': order.reference_id,
        'razorpay_order_id': order.razorpay_order_id,
        'razorpay_payment_id': order.razorpay_payment_id or None,
        'payment_method': order.payment_method or None,
        'payment_method_label': payment_method_label(order.payment_method)
        if order.payment_method
        else None,
        'shop_ids': order.shop_ids or [],
        'error_message': order.error_message or '',
        'created_at': order.created_at.isoformat(),
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
    }


def seller_razorpay_order_item(order):
    from easyudhar.payment_utils import payment_method_label

    return {
        'id': str(order.id),
        'source': 'seller_app',
        'customer_id': order.customer.linked_customer_id,
        'customer_name': order.customer.name,
        'seller_id': order.seller_id,
        'seller_name': order.seller.business_name,
        'customer_name_on_ledger': order.customer.name,
        'amount': float(order.amount),
        'currency': order.currency,
        'status': order.status,
        'reference_id': order.reference_id,
        'razorpay_order_id': order.razorpay_order_id,
        'razorpay_payment_id': order.razorpay_payment_id or None,
        'payment_method': order.payment_method or None,
        'payment_method_label': payment_method_label(order.payment_method)
        if order.payment_method
        else None,
        'note': order.note or '',
        'error_message': order.error_message or '',
        'created_at': order.created_at.isoformat(),
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
    }


def seller_payment_link_item(link):
    payments_count = getattr(link, 'payments_count', None)
    if payments_count is None:
        payments_count = link.payments.count()
    return {
        'id': str(link.id),
        'seller_id': link.seller_id,
        'seller_name': link.seller.business_name,
        'customer_id': link.customer.linked_customer_id,
        'seller_customer_id': str(link.customer_id),
        'customer_name': link.customer.name,
        'max_amount': float(link.max_amount),
        'amount_received': float(link.amount_received),
        'amount_remaining': float(link.amount_remaining),
        'status': link.status,
        'reference_id': link.reference_id,
        'razorpay_payment_link_id': link.razorpay_payment_link_id,
        'short_url': link.short_url,
        'note': link.note or '',
        'payments_count': payments_count,
        'expire_at': link.expire_at.isoformat() if link.expire_at else None,
        'created_at': link.created_at.isoformat(),
        'paid_at': link.paid_at.isoformat() if link.paid_at else None,
    }


def customer_saved_payment_method_item(method):
    from easyudhar.payment_utils import payment_method_label

    return {
        'id': str(method.id),
        'customer_id': method.user_id,
        'customer_name': method.user.full_name or method.user.email,
        'method_type': method.method_type,
        'method_label': payment_method_label(method.method_type),
        'label': method.label or '',
        'upi_id': method.upi_id or '',
        'account_ref': method.account_ref or '',
        'is_default': method.is_default,
        'created_at': method.created_at.isoformat(),
    }


def seller_notification_item(n):
    return {
        'id': str(n.id),
        'seller_id': n.seller_id,
        'type': n.notification_type,
        'title': n.title,
        'body': n.subtitle,
        'channel': 'in_app',
        'status': 'sent',
        'created_at': n.created_at.isoformat(),
    }


def customer_notification_item(n):
    return {
        'id': str(n.id),
        'customer_id': n.user_id,
        'type': n.notification_type,
        'title': n.title,
        'body': n.subtitle,
        'read': n.is_read,
        'created_at': n.created_at.isoformat(),
    }


def device_token_item(token, *, platform, preview, last_active, created_at):
    return {
        'id': str(token.id),
        'device_name': token.device_id or '',
        'platform': platform,
        'fcm_token_preview': preview,
        'last_active_at': last_active,
        'created_at': created_at,
    }


def seller_device_item(dt):
    from adminapp.utils import mask_token

    return device_token_item(
        dt,
        platform=dt.platform,
        preview=mask_token(dt.token),
        last_active=dt.updated_at.isoformat(),
        created_at=dt.created_at.isoformat(),
    )


def customer_device_item(dt):
    from adminapp.utils import mask_token

    return device_token_item(
        dt,
        platform=dt.platform,
        preview=mask_token(dt.token),
        last_active=dt.updated_at.isoformat(),
        created_at=dt.created_at.isoformat(),
    )


def customer_backup_item(backup):
    from adminapp.services.backups import backup_summary

    return {
        'id': backup.id,
        'customer_id': backup.customer_id,
        'label': backup.label,
        'summary': backup_summary(backup.payload),
        'created_by': backup.created_by.full_name if backup.created_by_id else None,
        'created_at': backup.created_at.isoformat(),
        'restored_by': backup.restored_by.full_name if backup.restored_by_id else None,
        'restored_at': backup.restored_at.isoformat() if backup.restored_at else None,
    }


def shop_message_item(msg):
    customer_id = msg.customer_user_id or (
        msg.seller_customer.linked_customer_id if msg.seller_customer_id else None
    )
    return {
        'id': str(msg.id),
        'seller_id': msg.seller_id,
        'customer_id': customer_id,
        'sender_type': msg.sender,
        'body': msg.message or '',
        'flagged': getattr(msg, 'flagged', False),
        'created_at': msg.created_at.isoformat(),
    }


def _reminder_message_body(log):
    if log.message_body:
        return log.message_body
    if log.channel != ReminderLog.CHANNEL_SMS:
        return ''
    try:
        from sellerapp.nimbus_sms import build_reminder_sms_text

        return build_reminder_sms_text(seller=log.seller, customer=log.customer)
    except Exception:
        return (
            f'Payment reminder for {log.customer.name}: outstanding '
            f'Rs. {log.customer.outstanding_amount} at {log.seller.business_name}.'
        )


def reminder_log_item(log):
    status = 'sent' if log.success else 'failed'
    recipient = log.recipient_phone or log.customer.phone
    message_body = _reminder_message_body(log)
    return {
        'id': str(log.id),
        'seller_id': log.seller_id,
        'seller_name': log.seller.business_name,
        'customer_id': str(log.customer_id),
        'customer_name': log.customer.name,
        'channel': log.channel,
        'type': log.reminder_type,
        'template_id': log.template_id or '',
        'template_name': log.template_id or '',
        'message_body': message_body,
        'message': message_body,
        'recipient': recipient,
        'recipient_phone': recipient,
        'status': status,
        'success': log.success,
        'error_message': log.error_message,
        'provider_message_id': log.provider_message_id or '',
        'delivery_report': log.delivery_report or '',
        'created_at': log.sent_at.isoformat(),
        'sent_at': log.sent_at.isoformat(),
    }
