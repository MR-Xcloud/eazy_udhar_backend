from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Seed seller + customer demo data for full UI testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing demo data before seeding.',
        )
        parser.add_argument(
            '--phone',
            default='9876543210',
            help='Demo customer phone (default: 9876543210)',
        )
        parser.add_argument(
            '--email',
            default='anita@example.com',
            help='Demo customer email (default: anita@example.com)',
        )

    def handle(self, *args, **options):
        clear = ['--clear'] if options['clear'] else []
        self.stdout.write('Seeding seller demo data…')
        call_command('seed_seller_data', *clear)
        self.stdout.write('Seeding customer demo data…')
        call_command(
            'seed_customer_data',
            *clear,
            phone=options['phone'],
            email=options['email'],
        )
        self.stdout.write(self.style.SUCCESS('\nAll demo data ready.\n'))
        self.stdout.write('Customer login: anita@example.com / password123')
        self.stdout.write('Seller login:   seller@example.com / password123')
