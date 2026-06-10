from django.utils import timezone

from .models import ReminderLog, Seller, SellerSettings
from .reminders import customers_for_auto_remind, send_customer_reminder


def _parse_hhmm(value):
    try:
        hour, minute = value.split(':')
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        return 9, 0


def is_auto_remind_due_now(settings_row, now=None):
    now = now or timezone.localtime()
    hour, minute = _parse_hhmm(settings_row.auto_remind_time)
    return now.hour == hour and now.minute < 15


def run_auto_reminders(*, force=False):
    results = []
    for seller in Seller.objects.select_related('settings').all():
        settings, _ = SellerSettings.objects.get_or_create(seller=seller)
        if not settings.auto_remind_enabled and not force:
            continue
        if not force and not is_auto_remind_due_now(settings):
            continue

        channels = [c.lower() for c in (settings.reminder_channels or ['sms'])]
        customers = customers_for_auto_remind(seller, settings.auto_remind_days_before)
        for customer in customers:
            try:
                channel_results = send_customer_reminder(
                    seller,
                    customer,
                    channels=channels,
                    reminder_type=ReminderLog.TYPE_AUTO,
                    skip_if_sent_today=True,
                )
                results.append(
                    {
                        'seller': seller.business_name,
                        'customer': customer.name,
                        'channels': channel_results,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        'seller': seller.business_name,
                        'customer': customer.name,
                        'error': str(exc),
                    }
                )
    return results
