from django.core.management.base import BaseCommand

from sellerapp.auto_reminders import run_auto_reminders


class Command(BaseCommand):
    help = 'Send automatic payment reminders per seller settings (schedule hourly cron).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Run for all enabled sellers regardless of auto_remind_time',
        )

    def handle(self, *args, **options):
        results = run_auto_reminders(force=options['force'])
        self.stdout.write(self.style.SUCCESS(f'Processed {len(results)} customer reminder(s)'))
        for row in results:
            self.stdout.write(f"  {row}")
