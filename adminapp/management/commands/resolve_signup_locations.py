"""Resolve signup cities for accounts that have an IP but no location yet.

The geo lookup at registration runs in a background thread, so it can lose a
race with a restart or a provider outage. This command picks up whatever it
missed — safe to run on a schedule.

    python manage.py resolve_signup_locations
    python manage.py resolve_signup_locations --recheck   # re-resolve everything
"""

import time

from django.core.management.base import BaseCommand

from customerapp.models import Customer
from easyudhar.signup_location import resolve_for
from sellerapp.models import Seller


class Command(BaseCommand):
    help = 'Fill in signup city/region/country for accounts that have a signup IP.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--recheck',
            action='store_true',
            help='Re-resolve accounts that already have a location.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Stop after this many accounts per model (0 = no limit).',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.5,
            help='Seconds between lookups — keeps free HTTP providers happy.',
        )

    def handle(self, *args, **options):
        for model, label in ((Seller, 'sellers'), (Customer, 'customers')):
            qs = model.objects.exclude(signup_ip=None).exclude(signup_ip='')
            if not options['recheck']:
                qs = qs.filter(signup_city='')
            qs = qs.order_by('id')
            if options['limit']:
                qs = qs[: options['limit']]

            resolved = failed = 0
            for user in qs:
                if resolve_for(user):
                    resolved += 1
                    self.stdout.write(f'  #{user.pk} → {user.signup_location}')
                else:
                    failed += 1
                if options['delay']:
                    time.sleep(options['delay'])

            self.stdout.write(
                self.style.SUCCESS(f'{label}: {resolved} resolved, {failed} unresolved')
            )
