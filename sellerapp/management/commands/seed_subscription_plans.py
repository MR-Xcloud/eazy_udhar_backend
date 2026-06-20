from django.core.management.base import BaseCommand

from adminapp.models import SubscriptionPlan


PLANS = [
    {
        'name': 'Basic (Free)',
        'slug': 'basic-free',
        'price_monthly': 0,
        'price_yearly': 0,
        'trial_days': 0,
        'sort_order': 1,
        'features': {
            'message_limit': 0,
            'reminder_type': 'on_demand',
            'reminder_label': 'On-demand reminders',
            'is_free': True,
            'purchasable': False,
        },
    },
    {
        'name': 'Basic (Paid)',
        'slug': 'basic-paid',
        'price_monthly': 29,
        'price_yearly': 348,
        'trial_days': 0,
        'sort_order': 2,
        'features': {
            'message_limit': 100,
            'reminder_type': 'on_demand',
            'reminder_label': 'On-demand reminders',
            'purchasable': True,
        },
    },
    {
        'name': 'Basic Plus',
        'slug': 'basic-plus',
        'price_monthly': 49,
        'price_yearly': 588,
        'trial_days': 0,
        'sort_order': 3,
        'features': {
            'message_limit': 250,
            'reminder_type': 'on_demand',
            'reminder_label': 'On-demand reminders',
            'purchasable': True,
        },
    },
    {
        'name': 'Basic Pro',
        'slug': 'basic-pro',
        'price_monthly': 99,
        'price_yearly': 1188,
        'trial_days': 0,
        'sort_order': 4,
        'features': {
            'message_limit': 750,
            'reminder_type': 'on_demand',
            'reminder_label': 'On-demand reminders',
            'purchasable': True,
        },
    },
    {
        'name': 'Growth (Best Value)',
        'slug': 'growth-best-value',
        'price_monthly': 199,
        'price_yearly': 2388,
        'trial_days': 0,
        'sort_order': 5,
        'features': {
            'message_limit': 1250,
            'reminder_type': 'on_demand',
            'reminder_label': 'On-demand reminders',
            'badge': 'best_value',
            'purchasable': True,
        },
    },
    {
        'name': 'Growth Pro',
        'slug': 'growth-pro',
        'price_monthly': 299,
        'price_yearly': 3588,
        'trial_days': 0,
        'sort_order': 6,
        'features': {
            'message_limit': 2000,
            'reminder_type': 'on_demand',
            'reminder_label': 'On-demand reminders',
            'purchasable': True,
        },
    },
    {
        'name': 'Business Pro',
        'slug': 'business-pro',
        'price_monthly': 499,
        'price_yearly': 5988,
        'trial_days': 0,
        'sort_order': 7,
        'features': {
            'message_limit': 4500,
            'reminder_type': 'automated',
            'reminder_label': 'Automated daily reminders (monthly cap)',
            'purchasable': True,
        },
    },
    {
        'name': 'Business Premium',
        'slug': 'business-premium',
        'price_monthly': 799,
        'price_yearly': 9588,
        'trial_days': 0,
        'sort_order': 8,
        'features': {
            'message_limit': 6500,
            'reminder_type': 'automated',
            'reminder_label': 'Automated daily reminders (monthly cap)',
            'purchasable': True,
        },
    },
    {
        'name': 'Business Max',
        'slug': 'business-max',
        'price_monthly': 999,
        'price_yearly': 11988,
        'trial_days': 0,
        'sort_order': 9,
        'features': {
            'message_limit': 10000,
            'reminder_type': 'automated',
            'reminder_label': 'Automated daily reminders (monthly cap)',
            'purchasable': True,
        },
    },
]


class Command(BaseCommand):
    help = 'Seed seller subscription plans (monthly/yearly tiers).'

    def handle(self, *args, **options):
        for plan_data in PLANS:
            SubscriptionPlan.objects.update_or_create(
                slug=plan_data['slug'],
                defaults=plan_data,
            )
        self.stdout.write(
            self.style.SUCCESS(f'Seeded {len(PLANS)} subscription plans')
        )
