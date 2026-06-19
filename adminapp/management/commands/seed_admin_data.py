from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from adminapp.models import (
    AdminUser,
    CronJobStatus,
    SubscriptionPlan,
)


class Command(BaseCommand):
    help = 'Seed admin user, subscription plans, and cron job definitions.'

    def handle(self, *args, **options):
        admin, created = AdminUser.objects.get_or_create(
            email='admin@eazyudhar.com',
            defaults={
                'full_name': 'Super Admin',
                'role': AdminUser.ROLE_SUPER_ADMIN,
                'is_staff': True,
                'is_active': True,
            },
        )
        if created:
            admin.set_password('Admin@2026')
            admin.save()
            self.stdout.write(self.style.SUCCESS('Created admin@eazyudhar.com / Admin@2026'))
        else:
            self.stdout.write('Admin user already exists')

        plans = [
            {
                'name': 'Free Trial',
                'slug': 'free-trial',
                'price_monthly': 0,
                'price_yearly': 0,
                'trial_days': 14,
                'features': ['Up to 50 customers', 'SMS reminders', 'Basic reports'],
                'sort_order': 1,
            },
            {
                'name': 'Basic',
                'slug': 'basic',
                'price_monthly': 299,
                'price_yearly': 2990,
                'trial_days': 0,
                'features': ['Unlimited customers', 'SMS + WhatsApp', 'Daily summary'],
                'sort_order': 2,
            },
            {
                'name': 'Pro',
                'slug': 'pro',
                'price_monthly': 599,
                'price_yearly': 5990,
                'trial_days': 0,
                'features': ['Everything in Basic', 'Team members', 'Priority support'],
                'sort_order': 3,
            },
        ]
        for plan_data in plans:
            SubscriptionPlan.objects.update_or_create(
                slug=plan_data['slug'],
                defaults=plan_data,
            )
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(plans)} subscription plans'))

        cron_jobs = [
            ('run_auto_reminders', '0 * * * *'),
            ('send_daily_summary', '0 * * * *'),
            ('send_nightly_sms', '30 15 * * *'),
        ]
        for name, schedule in cron_jobs:
            CronJobStatus.objects.update_or_create(
                name=name,
                defaults={
                    'schedule': schedule,
                    'last_status': CronJobStatus.LAST_STATUS_NEVER,
                },
            )
        self.stdout.write(self.style.SUCCESS('Seeded cron job definitions'))
