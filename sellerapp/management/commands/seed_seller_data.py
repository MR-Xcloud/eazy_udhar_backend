from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from sellerapp.models import (
    CustomerNote,
    LedgerTransaction,
    Seller,
    SellerCustomer,
    SellerSettings,
    TeamMember,
)
from sellerapp.services import add_credit, receive_payment

DEMO_EMAIL = 'seller@example.com'
DEMO_PASSWORD = 'password123'


class Command(BaseCommand):
    help = 'Seed demo seller + customers + transactions for UI testing.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            Seller.objects.filter(email=DEMO_EMAIL).delete()
            self.stdout.write('Cleared demo seller data.')

        seller, created = Seller.objects.get_or_create(
            email=DEMO_EMAIL,
            defaults={
                'username': DEMO_EMAIL,
                'full_name': 'Ramesh Kumar',
                'business_name': 'Ramesh Kirana',
                'phone': '9876543210',
                'role': Seller.ROLE_SELLER,
                'address': 'Main Bazaar, Delhi',
                'gst_number': '07ABCDE1234F1Z5',
            },
        )
        seller.set_password(DEMO_PASSWORD)
        seller.save()

        SellerSettings.objects.get_or_create(
            seller=seller,
            defaults={'language': 'en', 'reminder_channels': ['whatsapp', 'sms']},
        )

        if not seller.team_members.exists():
            TeamMember.objects.create(seller=seller, name='Suresh', phone='9999900001', role='staff')
            TeamMember.objects.create(seller=seller, name='Priya', phone='9999900002', role='cashier')

        customers_data = [
            ('Anita Sharma', '9876543210', Decimal('12450'), SellerCustomer.STATUS_PENDING),
            ('Gupta Stores', '+91 91234 56780', Decimal('8200'), SellerCustomer.STATUS_OVERDUE),
            ('Patel Hardware', '+91 99887 76655', Decimal('5600'), SellerCustomer.STATUS_PENDING),
            ('Metro Supplies', '+91 90001 11223', Decimal('0'), SellerCustomer.STATUS_SETTLED),
            ('Singh Electronics', '+91 98123 45678', Decimal('21650'), SellerCustomer.STATUS_OVERDUE),
        ]

        customers = []
        for name, phone, outstanding, status in customers_data:
            c, _ = SellerCustomer.objects.get_or_create(
                seller=seller,
                phone=phone,
                defaults={
                    'name': name,
                    'outstanding_amount': outstanding,
                    'status': status,
                    'email': f'{phone.replace(" ", "").replace("+", "")}@demo.local',
                },
            )
            c.name = name
            c.outstanding_amount = outstanding
            c.status = status
            c.save()
            customers.append(c)

        from customerapp.messaging import link_seller_customer
        for c in customers:
            link_seller_customer(c)

        if not LedgerTransaction.objects.filter(seller=seller).exists():
            c0 = customers[0]
            add_credit(seller, c0, Decimal('5500'), '10 bags rice', send_sms=False)
            receive_payment(seller, c0, Decimal('3000'), 'UPI', 'Partial payment', send_sms=False)
            add_credit(seller, customers[1], Decimal('8200'), 'Monthly stock', send_sms=False)
            add_credit(seller, customers[4], Decimal('10000'), 'Electronics order', send_sms=False)
            receive_payment(seller, customers[4], Decimal('5000'), 'Cash', send_sms=False)
            add_credit(seller, customers[2], Decimal('5600'), 'Tools on credit', send_sms=False)

            for c in customers[:3]:
                if not CustomerNote.objects.filter(customer=c).exists():
                    CustomerNote.objects.create(
                        customer=c,
                        seller=seller,
                        text=f'{c.name} prefers WhatsApp reminders on weekends.',
                    )

        self.stdout.write(self.style.SUCCESS('\nSeller seed complete!\n'))
        self.stdout.write(f'  Email:    {DEMO_EMAIL}')
        self.stdout.write(f'  Password: {DEMO_PASSWORD}')
        self.stdout.write(f'  Login:    POST /auth/seller/login')
