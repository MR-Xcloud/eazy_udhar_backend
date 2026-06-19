from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from sellerapp.daily_sms import send_pending_digests


class Command(BaseCommand):
    help = (
        'Send one merged digest SMS per customer phone for the given date '
        '(all shops combined). Schedule nightly on Render cron, e.g. 21:00 IST.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Activity date YYYY-MM-DD (default: today in Asia/Kolkata)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Resend even if SMS was already sent for that digest',
        )

    def handle(self, *args, **options):
        activity_date = options.get('date')
        if activity_date:
            activity_date = datetime.strptime(activity_date, '%Y-%m-%d').date()
        else:
            activity_date = timezone.localdate()

        results = send_pending_digests(activity_date=activity_date, force=options['force'])
        sent = sum(1 for r in results if r.get('sent'))
        failed = len(results) - sent
        self.stdout.write(
            self.style.SUCCESS(
                f'Date {activity_date}: {sent} sent, {failed} failed/skipped ({len(results)} total)'
            )
        )
        for row in results:
            status = 'SENT' if row.get('sent') else 'SKIP'
            shops = row.get('shops', 1)
            self.stdout.write(
                f"  [{status}] {row.get('customer')} ({shops} shop(s)) — "
                f"{row.get('error') or row.get('statement_url', '')}"
            )
