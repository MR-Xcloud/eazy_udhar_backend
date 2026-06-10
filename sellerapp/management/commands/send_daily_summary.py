from django.core.management.base import BaseCommand

from sellerapp.daily_summary import run_daily_summaries


class Command(BaseCommand):
    help = 'Send daily business summary SMS/push to sellers (schedule hourly cron).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Send now for all enabled sellers regardless of daily_summary_time',
        )

    def handle(self, *args, **options):
        results = run_daily_summaries(force=options['force'])
        sent = sum(1 for r in results if not r.get('skipped') and not r.get('error'))
        self.stdout.write(self.style.SUCCESS(f'Daily summary run: {sent} seller(s) processed'))
        for row in results:
            self.stdout.write(f"  {row}")
