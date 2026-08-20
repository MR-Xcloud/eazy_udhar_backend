"""Retry backstop for subscription invoices that never fully reached the CRM
finance module — CRM down, network blip, token rotated mid-flight.

Two legs per invoice: the sale (crm_invoice_sync) and the money against it
(crm_receipt_sync). Either can fail on its own, so both are retried, and an
invoice counts as done only when both are synced. Both endpoints are idempotent
on the invoice number, so re-pushing a synced invoice is harmless.
"""

from django.core.management.base import BaseCommand

from adminapp.models import SubscriptionInvoice
from adminapp.services.crm_invoice_sync import push
from adminapp.services.crm_receipt_sync import push as push_receipt


class Command(BaseCommand):
    help = 'Push paid EazyUdhar subscription invoices into the CRM finance module'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all', action='store_true',
            help='Re-push every paid invoice, not just unsynced ones',
        )
        parser.add_argument(
            '--dry', action='store_true',
            help='List what would be pushed, change nothing',
        )

    def handle(self, *args, **options):
        qs = (
            SubscriptionInvoice.objects
            .select_related('seller', 'subscription__plan')
            .filter(status=SubscriptionInvoice.STATUS_PAID)
            .order_by('id')
        )

        if not options['all']:
            # Either leg outstanding is reason enough to pick the invoice up;
            # the pushes themselves no-op on the leg that is already done.
            qs = qs.exclude(crm_sync_status='synced', crm_receipt_sync_status='synced')

        invoices = list(qs)
        if not invoices:
            self.stdout.write('Nothing to sync.')
            return

        self.stdout.write(f'{len(invoices)} invoice(s) to push.')
        ok = fail = 0

        for invoice in invoices:
            total = invoice.amount + invoice.tax_amount
            if options['dry']:
                self.stdout.write(f'  would push {invoice.invoice_number} (₹{total})')
                continue

            # --all means "re-push regardless"; otherwise skip a leg that is
            # already synced rather than making a pointless idempotent call.
            force = options['all']
            invoice_ok = (
                not force and invoice.crm_sync_status == invoice.CRM_SYNC_SYNCED
            ) or push(invoice)
            receipt_ok = invoice_ok and ((
                not force and invoice.crm_receipt_sync_status == invoice.CRM_SYNC_SYNCED
            ) or push_receipt(invoice))

            if invoice_ok and receipt_ok:
                ok += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ {invoice.invoice_number} → {invoice.crm_invoice_no or "?"}'
                    f' / {invoice.crm_receipt_no or "?"}'
                ))
            else:
                fail += 1
                leg = 'invoice' if not invoice_ok else 'receipt'
                self.stderr.write(f'  ✗ {invoice.invoice_number} ({leg}) — see log')

        if not options['dry']:
            self.stdout.write(f'Done. {ok} synced, {fail} failed.')
