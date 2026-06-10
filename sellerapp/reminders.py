"""Manual and automatic customer reminders via SMS, WhatsApp, and push."""

from django.utils import timezone

from customerapp.messaging import (
    ensure_customer_account,
    link_seller_customer,
    normalize_phone,
    notify_customer_event,
)
from customerapp.models import CustomerNotification

from .models import CustomerReminder, ReminderLog, SellerCustomer, SellerSettings
from .nimbus_sms import send_reminder_sms
from .whatsapp import send_whatsapp_reminder


def _format_mobile_e164(phone):
    digits = normalize_phone(phone)
    if len(digits) == 10:
        return f'+91{digits}'
    return phone


def _build_reminder_message(customer, seller):
    return (
        f'Reminder from {seller.business_name}: Dear {customer.name}, '
        f'your outstanding balance is Rs. {customer.outstanding_amount}. '
        f'Please pay at the earliest. - EAZYUDHAR'
    )


def _already_sent_today(seller, customer, channel, reminder_type):
    today = timezone.localdate()
    return ReminderLog.objects.filter(
        seller=seller,
        customer=customer,
        channel=channel,
        reminder_type=reminder_type,
        sent_at__date=today,
        success=True,
    ).exists()


def _log_reminder(seller, customer, channel, reminder_type, success, error=''):
    ReminderLog.objects.create(
        seller=seller,
        customer=customer,
        channel=channel,
        reminder_type=reminder_type,
        success=success,
        error_message=(error or '')[:500],
    )


def send_customer_reminder(
    seller,
    customer,
    *,
    channels,
    reminder_type=ReminderLog.TYPE_MANUAL,
    skip_if_sent_today=False,
    message=None,
):
    """
    Send reminder on requested channels.
    Returns dict with sms/whatsapp/push results per app contract.
    """
    message = message or _build_reminder_message(customer, seller)
    mobile_display = _format_mobile_e164(customer.phone)
    results = {}

    if 'sms' in channels:
        if skip_if_sent_today and _already_sent_today(
            seller, customer, ReminderLog.CHANNEL_SMS, reminder_type
        ):
            results['sms'] = {
                'sent': False,
                'channel': 'sms',
                'to': mobile_display,
                'error': 'Already sent today',
                'skipped': True,
            }
        else:
            sms_result = send_reminder_sms(
                seller=seller,
                customer=customer,
                message=message,
            )
            sent = bool(sms_result.get('sent'))
            results['sms'] = {
                'sent': sent,
                'channel': 'sms',
                'to': mobile_display,
                'error': sms_result.get('error', ''),
                'message_id': sms_result.get('message_id', ''),
            }
            _log_reminder(
                seller,
                customer,
                ReminderLog.CHANNEL_SMS,
                reminder_type,
                sent,
                sms_result.get('error', ''),
            )

    if 'whatsapp' in channels:
        if skip_if_sent_today and _already_sent_today(
            seller, customer, ReminderLog.CHANNEL_WHATSAPP, reminder_type
        ):
            results['whatsapp'] = {
                'sent': False,
                'channel': 'whatsapp',
                'to': mobile_display,
                'error': 'Already sent today',
                'skipped': True,
            }
        else:
            wa_result = send_whatsapp_reminder(
                seller=seller,
                customer=customer,
                message=message,
            )
            sent = bool(wa_result.get('sent'))
            results['whatsapp'] = {
                'sent': sent,
                'channel': 'whatsapp',
                'to': mobile_display,
                'error': wa_result.get('error', ''),
            }
            _log_reminder(
                seller,
                customer,
                ReminderLog.CHANNEL_WHATSAPP,
                reminder_type,
                sent,
                wa_result.get('error', ''),
            )

    if 'push' in channels:
        customer_user = link_seller_customer(customer)
        push_sent = False
        push_error = ''
        if customer_user:
            account = ensure_customer_account(customer, customer_user)
            from easyudhar.fcm import push_customer_notification

            notification = CustomerNotification.objects.create(
                user=customer_user,
                notification_type=CustomerNotification.TYPE_REMINDER,
                title=f'Reminder from {seller.business_name}',
                subtitle=message[:500],
                shop_account=account,
                reference_id=str(customer.id),
                is_read=False,
            )
            count = push_customer_notification(notification)
            push_sent = count > 0
            if not push_sent:
                push_error = 'Push not delivered (disabled or no device token)'
        else:
            push_error = 'Customer app account not linked'
        results['push'] = {
            'sent': push_sent,
            'channel': 'push',
            'to': customer_user.email if customer_user else '',
            'error': push_error,
        }
        _log_reminder(
            seller,
            customer,
            ReminderLog.CHANNEL_PUSH,
            reminder_type,
            push_sent,
            push_error,
        )

    CustomerReminder.objects.create(
        customer=customer,
        seller=seller,
        channels=channels,
        message=message,
        is_sent=any(r.get('sent') for r in results.values()),
    )

    # In-app notification for linked customer (if not already via push channel)
    if 'push' not in channels:
        customer_user = link_seller_customer(customer)
        if customer_user:
            account = ensure_customer_account(customer, customer_user)
            notify_customer_event(
                customer_user,
                account,
                notification_type=CustomerNotification.TYPE_REMINDER,
                title=f'Reminder from {seller.business_name}',
                subtitle=message[:500],
                reference_id=str(customer.id),
            )

    return results


def resolve_reminder_channels(seller, channels=None):
    if channels:
        return [c.lower().strip() for c in channels]
    settings, _ = SellerSettings.objects.get_or_create(seller=seller)
    return [c.lower() for c in (settings.reminder_channels or ['whatsapp', 'sms'])]


def customers_for_auto_remind(seller, days_before=1):
    """Customers with outstanding balance due for automatic reminder."""
    qs = SellerCustomer.objects.filter(seller=seller, outstanding_amount__gt=0)
    if days_before <= 0:
        return qs.filter(status=SellerCustomer.STATUS_OVERDUE)
    return qs.filter(
        status__in=[SellerCustomer.STATUS_OVERDUE, SellerCustomer.STATUS_PENDING]
    )
