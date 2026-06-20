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
DEMO_PHONE = '9876543210'
DEMO_PASSWORD = 'password123'
DEMO_NAME = 'Anita Sharma'


class Command(BaseCommand):
    help = 'Seed demo data for customer app APIs (UI testing).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Remove existing seed data for the demo user before seeding.',
        )
        parser.add_argument(
            '--email',
            default=DEMO_EMAIL,
            help=f'Demo customer email (default: {DEMO_EMAIL})',
        )
        parser.add_argument(
            '--phone',
            default=DEMO_PHONE,
            help=f'Demo customer phone (default: {DEMO_PHONE})',
        )
        parser.add_argument(
            '--name',
            default=DEMO_NAME,
            help=f'Demo customer name (default: {DEMO_NAME})',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.now().date()
        email = options['email'].strip().lower()
        phone = options['phone'].strip()
        name = options['name'].strip() or DEMO_NAME

        user = Customer.objects.filter(email=email).first()
        if user is None:
            user = Customer.objects.filter(phone=phone).first()

        if user is None:
            user = Customer.objects.create(
                email=email,
                username=email,
                full_name=name,
                phone=phone,
                role=Customer.ROLE_CUSTOMER,
            )
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created demo user: {email}'))
        else:
            user.email = email
            user.username = email
            user.full_name = name
            user.phone = phone
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(f'Using existing user: {email} ({phone})')

        if options['clear']:
            self._clear_user_data(user)

        settings, _ = CustomerSettings.objects.get_or_create(user=user)
        settings.language = 'en'
        settings.privacy_show_phone = True
        settings.privacy_show_email = False
        settings.keep_signed_in = True
        settings.push_notifications_enabled = True
        settings.save()

        accounts_data = [
            {
                'shop_name': 'Sharma Kirana Store',
                'outstanding_amount': Decimal('2500.00'),
                'advance_deposited': Decimal('500.00'),
                'advance_used': Decimal('200.00'),
                'next_due_date': today - timedelta(days=5),
                'status': CustomerAccount.STATUS_OVERDUE,
            },
            {
                'shop_name': 'Gupta General Store',
                'outstanding_amount': Decimal('1200.00'),
                'advance_deposited': Decimal('0.00'),
                'advance_used': Decimal('0.00'),
                'next_due_date': today + timedelta(days=10),
                'status': CustomerAccount.STATUS_ACTIVE,
            },
            {
                'shop_name': 'Patel Electronics',
                'outstanding_amount': Decimal('850.00'),
                'advance_deposited': Decimal('1300.00'),
                'advance_used': Decimal('1300.00'),
                'next_due_date': today + timedelta(days=3),
                'status': CustomerAccount.STATUS_ACTIVE,
            },
            {
                'shop_name': 'Metro Mart',
                'outstanding_amount': Decimal('4200.00'),
                'advance_deposited': Decimal('0.00'),
                'advance_used': Decimal('0.00'),
                'next_due_date': today - timedelta(days=2),
                'status': CustomerAccount.STATUS_OVERDUE,
            },
            {
                'shop_name': 'Rahul Medical Store',
                'outstanding_amount': Decimal('0.00'),
                'advance_deposited': Decimal('600.00'),
                'advance_used': Decimal('600.00'),
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
        self._seed_notifications(user, accounts, today)
        self._link_seller_accounts(user)
        self._attach_demo_seller(user, accounts)
        self._seed_chats(user, accounts)

        self.stdout.write(self.style.SUCCESS('\nCustomer seed complete!\n'))
        self.stdout.write(f'  Email:    {email}')
        self.stdout.write(f'  Phone:    {phone}')
        self.stdout.write(f'  Password: {DEMO_PASSWORD}')
        self.stdout.write('  Login:    POST /sapp/auth/customer/login')
        self.stdout.write(f'  Accounts: {len(accounts)} shops seeded')
        total_due = sum(a.outstanding_amount for a in accounts if a.has_balance)
        self.stdout.write(f'  Total due: Rs. {total_due}')
        unread = CustomerNotification.objects.filter(user=user, is_read=False).count()
        self.stdout.write(f'  Alerts:   {unread} unread notifications')

    def _clear_user_data(self, user):
        CustomerAccount.objects.filter(user=user).delete()
        CustomerPayment.objects.filter(user=user).delete()
        PaymentMethod.objects.filter(user=user).delete()
        CustomerNotification.objects.filter(user=user).delete()
        ShopMessage.objects.filter(customer_user=user).delete()
        self.stdout.write('Cleared existing demo data.')

    def _seed_statement(self, account, today):
        AccountStatementLine.objects.filter(account=account).delete()

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
        elif account.shop_name == 'Patel Electronics':
            lines = [
                ('TV on credit', Decimal('15000.00'), AccountStatementLine.TYPE_CREDIT, today - timedelta(days=45)),
                ('Advance deposit', Decimal('1300.00'), AccountStatementLine.TYPE_PAYMENT, today - timedelta(days=20)),
                ('Purchase paid from wallet balance', Decimal('850.00'), AccountStatementLine.TYPE_CREDIT, today - timedelta(days=3)),
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
        PaymentMethod.objects.filter(user=user).delete()

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
        CustomerPayment.objects.filter(user=user).delete()

        payments = [
            (accounts[0], Decimal('500.00'), 'upi', 'PAY-DEMO001', 7),
            (accounts[3], Decimal('800.00'), 'upi', 'PAY-DEMO002', 5),
            (accounts[1], Decimal('300.00'), 'cash', 'PAY-DEMO003', 2),
            (accounts[2], Decimal('1300.00'), 'upi', 'PAY-DEMO004', 20),
        ]
        for account, amount, method, ref, days_ago in payments:
            CustomerPayment.objects.create(
                user=user,
                account=account,
                amount=amount,
                method=method,
                status=CustomerPayment.STATUS_SUCCESS,
                reference_id=ref,
                created_at=timezone.now() - timedelta(days=days_ago),
            )

    def _seed_notifications(self, user, accounts, today):
        CustomerNotification.objects.filter(user=user).delete()

        by_name = {a.shop_name: a for a in accounts}
        items = [
            (
                CustomerNotification.TYPE_OVERDUE,
                'Payment overdue — Metro Mart',
                'Rs. 4,200 is overdue by 2 days',
                False,
                by_name.get('Metro Mart'),
            ),
            (
                CustomerNotification.TYPE_REMINDER,
                'Sharma Kirana — payment reminder',
                'Your due of Rs. 2,500 is overdue',
                False,
                by_name.get('Sharma Kirana Store'),
            ),
            (
                CustomerNotification.TYPE_MESSAGE,
                'New message from Patel Electronics',
                'Your wallet balance was used for your last purchase',
                False,
                by_name.get('Patel Electronics'),
            ),
            (
                CustomerNotification.TYPE_PAYMENT,
                'Payment successful',
                'Paid Rs. 800 to Metro Mart via UPI',
                True,
                by_name.get('Metro Mart'),
            ),
            (
                CustomerNotification.TYPE_CREDIT,
                'Credit added — Gupta General',
                'Rs. 1,200 outstanding on your account',
                True,
                by_name.get('Gupta General Store'),
            ),
            (
                CustomerNotification.TYPE_ADVANCE,
                'Advance deposited — Patel Electronics',
                'Rs. 1,300 added to your wallet',
                True,
                by_name.get('Patel Electronics'),
            ),
            (
                CustomerNotification.TYPE_GENERAL,
                'Welcome to EazyUdhar',
                'Track all your shop dues in one place',
                True,
                None,
            ),
            (
                CustomerNotification.TYPE_REMINDER,
                'Upcoming due — Gupta General',
                'Rs. 1,200 due in 10 days',
                True,
                by_name.get('Gupta General Store'),
            ),
        ]
        for i, (ntype, title, subtitle, is_read, account) in enumerate(items):
            CustomerNotification.objects.create(
                user=user,
                notification_type=ntype,
                title=title,
                subtitle=subtitle,
                shop_account=account,
                is_read=is_read,
                created_at=timezone.now() - timedelta(hours=i + 1),
            )

    def _link_seller_accounts(self, user):
        from customerapp.messaging import ensure_customer_account, link_seller_customer
        from sellerapp.models import Seller, SellerCustomer

        seller = Seller.objects.filter(email='seller@example.com').first()
        if not seller:
            self.stdout.write(
                self.style.WARNING(
                    '  Tip: run `python manage.py seed_seller_data` first to link seller chats.'
                )
            )
            return

        for sc in SellerCustomer.objects.filter(seller=seller):
            link_seller_customer(sc)
            if sc.linked_customer_id != user.id:
                continue
            account = ensure_customer_account(sc, user)
            account.outstanding_amount = sc.outstanding_amount
            account.shop_name = seller.business_name or sc.name
            account.has_balance = sc.outstanding_amount > 0
            account.save()

    def _attach_demo_seller(self, user, accounts):
        from sellerapp.models import Seller

        seller = Seller.objects.filter(email='seller@example.com').first()
        if not seller or not seller.upi_id:
            return
        for account in accounts:
            if account.seller_id:
                continue
            account.seller = seller
            account.save(update_fields=['seller', 'updated_at'])

    def _seed_chats(self, user, accounts):
        for account in CustomerAccount.objects.filter(user=user, seller_customer__isnull=False):
            sc = account.seller_customer
            seller = account.seller or sc.seller
            ShopMessage.objects.filter(seller_customer=sc, customer_user=user).delete()

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
