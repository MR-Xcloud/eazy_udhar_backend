from django.core.management.base import BaseCommand

from adminapp.models import SmsPack


PACKS = [
    {
        'name': '1000 SMS',
        'slug': 'sms-1000',
        'sms_quantity': 1000,
        'unit_price_paise': '25',
        'sort_order': 1,
    },
    {
        'name': '2500 SMS',
        'slug': 'sms-2500',
        'sms_quantity': 2500,
        'unit_price_paise': '22.5',
        'sort_order': 2,
    },
    {
        'name': '5000 SMS',
        'slug': 'sms-5000',
        'sms_quantity': 5000,
        'unit_price_paise': '20',
        'sort_order': 3,
    },
    {
        'name': '10000 SMS',
        'slug': 'sms-10000',
        'sms_quantity': 10000,
        'unit_price_paise': '15',
        'sort_order': 4,
    },
]


class Command(BaseCommand):
    help = 'Seed prepaid SMS packs (quantity + per-SMS paise + 18% GST).'

    def handle(self, *args, **options):
        for row in PACKS:
            SmsPack.objects.update_or_create(
                slug=row['slug'],
                defaults={
                    **row,
                    'gst_percent': 18,
                    'is_active': True,
                },
            )
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(PACKS)} SMS packs'))
