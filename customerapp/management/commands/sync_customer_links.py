from django.core.management.base import BaseCommand

from customerapp.messaging import link_seller_customer, sync_customer_from_seller_ledgers
from customerapp.models import Customer
from sellerapp.models import SellerCustomer


class Command(BaseCommand):
    help = 'Link seller ledger customers to app users and backfill chat notifications.'

    def handle(self, *args, **options):
        linked = 0
        for sc in SellerCustomer.objects.select_related('seller').all():
            before = sc.linked_customer_id
            user = link_seller_customer(sc)
            if user and not before:
                linked += 1
                self.stdout.write(
                    f'Linked {sc.name} ({sc.phone}) -> {user.email}'
                )

        synced_users = 0
        for user in Customer.objects.all():
            accounts = sync_customer_from_seller_ledgers(user)
            if accounts:
                synced_users += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. New links: {linked}, users synced: {synced_users}'
            )
        )
