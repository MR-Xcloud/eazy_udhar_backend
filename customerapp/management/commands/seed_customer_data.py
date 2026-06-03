from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from customerapp.models import (
    AccountStatementLine,
    Customer,
    CustomerAccount,
    CustomerNotification,
    CustomerPayment,
    CustomerSettings,
    PaymentMethod,
    ShopMessage,
)

DEMO_EMAIL = 'anita@example.com'
DEMO_PASSWORD = 'password123'


class Command(BaseCommand):
    help = 'Seed demo data for customer app APIs (UI testing).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Remove existing seed data for the demo user before seeding.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.now().date()

        user, created = Customer.objects.get_or_create(
            email=DEMO_EMAIL,
            defaults={
                'username': DEMO_EMAIL,
                'full_name': 'Anita Sharma',
                'phone': '9876543210',
                'role': Customer.ROLE_CUSTOMER,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created demo user: {DEMO_EMAIL}'))
        else:
            user.full_name = 'Anita Sharma'
            user.phone = '9876543210'
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(f'Using existing user: {DEMO_EMAIL}')

        if options['clear']:
            self._clear_user_data(user)

        settings, _ = CustomerSettings.objects.get_or_create(
            user=user,
            defaults={
                'language': 'en',
                'privacy_show_phone': False,
                'privacy_show_email': True,
                'keep_signed_in': True,
            },
        )
        settings.language = 'hi'
        settings.keep_signed_in = True
        settings.save()

        accounts_data = [
            {
                'shop_name': 'Sharma Kirana Store',
                'outstanding_amount': Decimal('2500.00'),
                'next_due_date': today - timedelta(days=5),
                'status': CustomerAccount.STATUS_OVERDUE,
            },
            {
                'shop_name': 'Gupta General Store',
                'outstanding_amount': Decimal('1200.00'),
                'next_due_date': today + timedelta(days=10),
                'status': CustomerAccount.STATUS_ACTIVE,
            },
            {
                'shop_name': 'Patel Electronics',
                'outstanding_amount': Decimal('850.00'),
                'next_due_date': today + timedelta(days=3),
                'status': CustomerAccount.STATUS_ACTIVE,
            },
            {
                'shop_name': 'Metro Mart',
                'outstanding_amount': Decimal('4200.00'),
                'next_due_date': today - timedelta(days=2),
                'status': CustomerAccount.STATUS_OVERDUE,
            },
            {
                'shop_name': 'Rahul Medical Store',
                'outstanding_amount': Decimal('0.00'),
                'next_due_date': None,
                'status': CustomerAccount.STATUS_CLEARED,
                'has_balance': False,
            },
        ]

        accounts = []
        for data in accounts_data:
            has_balance = data.pop('has_balance', True)
            account, _ = CustomerAccount.objects.get_or_create(
                user=user,
                shop_name=data['shop_name'],
                defaults={**data, 'has_balance': has_balance},
            )
            for key, value in data.items():
                setattr(account, key, value)
            account.has_balance = has_balance
            account.save()
            accounts.append(account)
            self._seed_statement(account, today)

        self._seed_payment_methods(user)
        self._seed_payments(user, accounts[:4], today)
        self._seed_notifications(user, today)
        self._link_seller_accounts(user)
        self._seed_chats(user, accounts)

        self.stdout.write(self.style.SUCCESS('\nSeed complete! Use these credentials in the app:\n'))
        self.stdout.write(f'  Email:    {DEMO_EMAIL}')
        self.stdout.write(f'  Password: {DEMO_PASSWORD}')
        self.stdout.write(f'  Login:    POST /auth/customer/login')
        self.stdout.write(f'  Accounts: {len(accounts)} shops seeded')
        total_due = sum(a.outstanding_amount for a in accounts if a.has_balance)
        self.stdout.write(f'  Total due: Rs. {total_due}')

    def _clear_user_data(self, user):
        CustomerAccount.objects.filter(user=user).delete()
        CustomerPayment.objects.filter(user=user).delete()
        PaymentMethod.objects.filter(user=user).delete()
        CustomerNotification.objects.filter(user=user).delete()
        ShopMessage.objects.filter(customer_user=user).delete()
        self.stdout.write('Cleared existing demo data.')

    def _seed_statement(self, account, today):
        if account.statement_lines.exists():
            return

        lines = [
            ('Udhar — monthly groceries', Decimal('1500.00'), AccountStatementLine.TYPE_CREDIT, today - timedelta(days=30)),
            ('Udhar — oil & rice', Decimal('1000.00'), AccountStatementLine.TYPE_CREDIT, today - timedelta(days=15)),
            ('Partial payment received', Decimal('500.00'), AccountStatementLine.TYPE_PAYMENT, today - timedelta(days=7)),
        ]
        if account.shop_name == 'Metro Mart':
            lines = [
                ('Bulk purchase — festival stock', Decimal('5000.00'), AccountStatementLine.TYPE_CREDIT, today - timedelta(days=20)),
                ('Payment via UPI', Decimal('800.00'), AccountStatementLine.TYPE_PAYMENT, today - timedelta(days=5)),
            ]
        elif account.shop_name == 'Rahul Medical Store':
            lines = [
                ('Medicines on credit', Decimal('600.00'), AccountStatementLine.TYPE_CREDIT, today - timedelta(days=40)),
                ('Full payment', Decimal('600.00'), AccountStatementLine.TYPE_PAYMENT, today - timedelta(days=10)),
            ]

        for desc, amount, line_type, date in lines:
            AccountStatementLine.objects.create(
                account=account,
                description=desc,
                amount=amount,
                line_type=line_type,
                date=date,
            )

    def _seed_payment_methods(self, user):
        if PaymentMethod.objects.filter(user=user).exists():
            return

        PaymentMethod.objects.create(
            user=user,
            method_type=PaymentMethod.TYPE_UPI,
            label='PhonePe UPI',
            upi_id='anita@ybl',
            is_default=True,
        )
        PaymentMethod.objects.create(
            user=user,
            method_type=PaymentMethod.TYPE_UPI,
            label='Google Pay',
            upi_id='anita.sharma@okaxis',
            is_default=False,
        )
        PaymentMethod.objects.create(
            user=user,
            method_type=PaymentMethod.TYPE_WALLET,
            label='Paytm Wallet',
            upi_id='',
            is_default=False,
        )

    def _seed_payments(self, user, accounts, today):
        if CustomerPayment.objects.filter(user=user).exists():
            return

        CustomerPayment.objects.create(
            user=user,
            account=accounts[0],
            amount=Decimal('500.00'),
            method='upi',
            status=CustomerPayment.STATUS_SUCCESS,
            reference_id='PAY-DEMO001',
            created_at=timezone.now() - timedelta(days=7),
        )
        CustomerPayment.objects.create(
            user=user,
            account=accounts[3],
            amount=Decimal('800.00'),
            method='upi',
            status=CustomerPayment.STATUS_SUCCESS,
            reference_id='PAY-DEMO002',
            created_at=timezone.now() - timedelta(days=5),
        )

    def _seed_notifications(self, user, today):
        if CustomerNotification.objects.filter(user=user).exists():
            return

        items = [
            (CustomerNotification.TYPE_REMINDER, 'Payment due at Metro Mart', '₹4,200 overdue since 2 days ago', False),
            (CustomerNotification.TYPE_REMINDER, 'Sharma Kirana — reminder', 'Your due of ₹2,500 is overdue', False),
            (CustomerNotification.TYPE_PAYMENT, 'Payment successful', 'Paid ₹800 to Metro Mart via UPI', True),
            (CustomerNotification.TYPE_GENERAL, 'Welcome to EasyUdhar', 'Track all your shop dues in one place', True),
            (CustomerNotification.TYPE_REMINDER, 'Upcoming due — Gupta General', '₹1,200 due in 10 days', True),
        ]
        for ntype, title, subtitle, is_read in items:
            CustomerNotification.objects.create(
                user=user,
                notification_type=ntype,
                title=title,
                subtitle=subtitle,
                is_read=is_read,
            )

    def _link_seller_accounts(self, user):
        from customerapp.messaging import ensure_customer_account, link_seller_customer
        from sellerapp.models import Seller, SellerCustomer

        seller = Seller.objects.filter(email='seller@example.com').first()
        if not seller:
            return

        for sc in SellerCustomer.objects.filter(seller=seller):
            link_seller_customer(sc)
            if sc.linked_customer_id != user.id:
                continue
            account = ensure_customer_account(sc, user)
            account.outstanding_amount = sc.outstanding_amount
            account.shop_name = seller.business_name
            account.has_balance = sc.outstanding_amount > 0
            account.save()

    def _seed_chats(self, user, accounts):
        for account in CustomerAccount.objects.filter(user=user, seller_customer__isnull=False):
            sc = account.seller_customer
            seller = account.seller or sc.seller
            if ShopMessage.objects.filter(seller_customer=sc, customer_user=user).exists():
                continue

            ShopMessage.objects.create(
                seller=seller,
                seller_customer=sc,
                customer_user=user,
                customer_account=account,
                sender=ShopMessage.SENDER_SELLER,
                message=(
                    f'Namaste! Your current balance at {account.shop_name} '
                    f'is Rs. {account.outstanding_amount}.'
                ),
            )
            ShopMessage.objects.create(
                seller=seller,
                seller_customer=sc,
                customer_user=user,
                customer_account=account,
                sender=ShopMessage.SENDER_CUSTOMER,
                message='Ok, I will pay by this weekend.',
            )
