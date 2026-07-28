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
    business = (seller.business_name or seller.full_name or 'your shop').strip()
    amount = customer.outstanding_amount
    upi = (getattr(seller, 'upi_id', None) or '').strip()
    lines = [
        f'Hello {customer.name},',
        '',
        (
            f'This is a payment reminder from {business}. '
            f'Your outstanding amount is Rs. {amount}.'
        ),
        '',
    ]
    if upi:
        lines.append(f'Please pay via UPI: {upi}')
        lines.append('Scan the QR code shared by the shop to pay this amount.')
        lines.append('')
    else:
        lines.append('Please make the payment when possible.')
        lines.append('')
    lines.append(f'- {business}')
    return '\n'.join(lines)


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


def log_sms_delivery(
    seller,
    customer,
    channel,
    reminder_type,
    success,
    error='',
    *,
    message_body='',
    template_id='',
    provider_message_id='',
    delivery_report='',
    recipient_phone='',
):
    """Persist an SMS / reminder send for admin comms logs."""
    ReminderLog.objects.create(
        seller=seller,
        customer=customer,
        channel=channel,
        reminder_type=reminder_type,
        success=success,
        error_message=(error or '')[:500],
        recipient_phone=(recipient_phone or customer.phone or '')[:20],
        message_body=(message_body or '')[:4000],
        template_id=(template_id or '')[:64],
        provider_message_id=(provider_message_id or '')[:128],
        delivery_report=(delivery_report or '')[:2000],
    )


def _log_reminder(
    seller,
    customer,
    channel,
    reminder_type,
    success,
    error='',
    *,
    message_body='',
    template_id='',
    provider_message_id='',
    delivery_report='',
    recipient_phone='',
):
    log_sms_delivery(
        seller,
        customer,
        channel,
        reminder_type,
        success,
        error,
        message_body=message_body,
        template_id=template_id,
        provider_message_id=provider_message_id,
        delivery_report=delivery_report,
        recipient_phone=recipient_phone,
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
    mobile_display = _format_mobile_e164(customer.phone)
    if not getattr(seller, 'is_active', True):
        skipped = {
            'sent': False,
            'error': 'Seller account suspended',
            'skipped': True,
        }
        return {
            'message': 'Seller account is suspended.',
            'sms': {**skipped, 'channel': 'sms', 'to': mobile_display},
            'whatsapp': {**skipped, 'channel': 'whatsapp', 'to': mobile_display},
            'push': {**skipped, 'channel': 'push', 'to': ''},
        }

    linked = getattr(customer, 'linked_customer', None)
    if linked is not None and not linked.is_active:
        skipped = {
            'sent': False,
            'error': 'Customer account suspended',
            'skipped': True,
        }
        return {
            'message': 'Customer account is suspended.',
            'sms': {**skipped, 'channel': 'sms', 'to': mobile_display},
            'whatsapp': {**skipped, 'channel': 'whatsapp', 'to': mobile_display},
            'push': {**skipped, 'channel': 'push', 'to': ''},
        }

    if customer.outstanding_amount <= 0:
        skipped = {
            'sent': False,
            'error': 'No outstanding balance',
            'skipped': True,
        }
        return {
            'message': 'Customer has no outstanding balance to remind.',
            'sms': {**skipped, 'channel': 'sms', 'to': mobile_display},
            'whatsapp': {**skipped, 'channel': 'whatsapp', 'to': mobile_display},
            'push': {**skipped, 'channel': 'push', 'to': ''},
        }

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
            if sent:
                from .sms_pack_service import consume_sms_pack_credit
                from .subscription_service import _sms_credits_from_pack

                pack_needed = _sms_credits_from_pack(seller, 1)
                if pack_needed > 0:
                    consume_sms_pack_credit(seller, pack_needed)
            _log_reminder(
                seller,
                customer,
                ReminderLog.CHANNEL_SMS,
                reminder_type,
                sent,
                sms_result.get('error', ''),
                message_body=sms_result.get('text') or message,
                template_id=sms_result.get('template_id', ''),
                provider_message_id=sms_result.get('message_id') or sms_result.get('reqid', ''),
                delivery_report=sms_result.get('delivery_report', ''),
                recipient_phone=customer.phone,
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
                message_body=message,
                recipient_phone=customer.phone,
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
                push_error = (
                    'Customer has not enabled app notifications. '
                    'Ask them to open the EazyUdhar app and allow notifications.'
                )
        else:
            push_error = (
                'Customer is not on the EazyUdhar app yet. '
                'Ask them to sign up with the same phone number.'
            )
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
            message_body=message,
            recipient_phone=customer.phone,
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
    from django.db.models import Q

    # Exclude linked app customers who are suspended; ledger-only contacts still allowed.
    qs = SellerCustomer.objects.filter(seller=seller, outstanding_amount__gt=0).filter(
        Q(linked_customer__isnull=True) | Q(linked_customer__is_active=True)
    )
    if days_before <= 0:
        return qs.filter(status=SellerCustomer.STATUS_OVERDUE)
    return qs.filter(
        status__in=[SellerCustomer.STATUS_OVERDUE, SellerCustomer.STATUS_PENDING]
    )
