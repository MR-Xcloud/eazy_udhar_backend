"""Local invoice numbering.

The number customers see comes from CRM finance (see `crm_invoice_sync`); this
series is the EazyUdhar-side reference, and the idempotency key for the push.
Shared by subscription and add-on invoices so the two never collide.
"""

from django.utils import timezone


def next_invoice_number():
    """INV-YYYYMM-#### sequential within the month, e.g. INV-202607-0001."""
    from ..models import SubscriptionInvoice

    now = timezone.now()
    prefix = f'INV-{now:%Y%m}-'
    count = SubscriptionInvoice.objects.filter(invoice_number__startswith=prefix).count()
    return f'{prefix}{count + 1:04d}'
