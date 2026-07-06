"""Send a test digest SMS with short statement link."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from customerapp.messaging import normalize_phone
from sellerapp.daily_sms import (
    ensure_nightly_digest,
    statement_link,
    statement_sms_link_for_digest,
)
from sellerapp.models import CustomerDayDigest, Seller, SellerCustomer
from sellerapp.nimbus_sms import send_merged_nightly_digest_sms
from sellerapp.services import add_credit


class Command(BaseCommand):
    help = 'Send test nightly digest SMS with short statement link (DLT-safe).'

    def add_arguments(self, parser):
        parser.add_argument('--phone', required=True, help='10-digit mobile number')
        parser.add_argument(
            '--amount',
            type=Decimal,
            default=Decimal('100'),
            help='Test credit amount (default 100)',
        )

    def handle(self, *args, **options):
        phone = normalize_phone(options['phone'])
        if len(phone) != 10:
            self.stderr.write(self.style.ERROR(f'Invalid phone: {options["phone"]!r}'))
            return

        customer = (
            SellerCustomer.objects.filter(phone=phone)
            .select_related('seller')
            .first()
        )
        if not customer:
            seller = Seller.objects.first()
            if not seller:
                self.stderr.write(self.style.ERROR('No seller in database.'))
                return
            customer = SellerCustomer.objects.filter(seller=seller).first()
            if not customer:
                self.stderr.write(self.style.ERROR('No seller customer in database.'))
                return
            customer.phone = phone
            customer.save(update_fields=['phone', 'updated_at'])
            self.stdout.write(
                f'Using customer {customer.name!r} — phone set to {phone}'
            )
        else:
            self.stdout.write(
                f'Customer: {customer.name!r} @ {customer.seller.business_name!r}'
            )

        seller = customer.seller
        tx, queued = add_credit(
            seller,
            customer,
            options['amount'],
            'Test SMS with statement link',
            send_sms=True,
        )
        self.stdout.write(f'Transaction id: {tx.id}')
        self.stdout.write(f'Queued: {queued.get("statement_sms_link")}')

        activity_date = timezone.localdate()
        digests = list(
            CustomerDayDigest.objects.filter(
                seller_customer__phone=phone,
                activity_date=activity_date,
                transaction_count__gt=0,
            ).select_related('seller_customer', 'seller_customer__seller')
        )
        if not digests:
            digests = list(
                CustomerDayDigest.objects.filter(
                    seller_customer=customer,
                    activity_date=activity_date,
                ).select_related('seller_customer', 'seller_customer__seller')
            )

        nightly = ensure_nightly_digest(phone, activity_date)
        sms_link = statement_sms_link_for_digest(nightly)
        full_url = statement_link(nightly.token)

        self.stdout.write(f'SMS short link (var3): {sms_link} (len={len(sms_link)})')
        self.stdout.write(f'Full statement URL: {full_url}')
        self.stdout.write(f'Short browser URL: https://{sms_link}')

        credit_total = sum((d.credit_total for d in digests), Decimal('0'))
        payment_total = sum((d.payment_total for d in digests), Decimal('0'))

        result = send_merged_nightly_digest_sms(
            phone=phone,
            digests=digests,
            nightly=nightly,
            credit_total=credit_total or options['amount'],
            payment_total=payment_total,
        )

        if result.get('sent'):
            self.stdout.write(self.style.SUCCESS(f'SMS sent to {phone}'))
            if result.get('delivery_report'):
                self.stdout.write(f'Delivery: {result["delivery_report"]}')
        else:
            self.stderr.write(
                self.style.ERROR(f'SMS failed: {result.get("error") or result}')
            )
