from django.core.management.base import BaseCommand

from sellerapp.eod_excel_report import run_eod_backups


class Command(BaseCommand):
    help = (
        'Email each active seller an Excel backup of their own ledger transactions, '
        'due at their configured daily summary time (schedule hourly cron).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Send now for all enabled sellers regardless of the scheduled time.',
        )

    def handle(self, *args, **options):
        results = run_eod_backups(force=options['force'])
        sent = sum(1 for r in results if r.get('sent'))
        self.stdout.write(self.style.SUCCESS(f'EOD Excel backup run: {sent} seller(s) emailed'))
        for row in results:
            self.stdout.write(f"  {row}")
