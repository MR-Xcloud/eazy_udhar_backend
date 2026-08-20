"""Emailing an invoice to the seller.

One path for both the admin panel's "Email" button and the automatic send on an
add-on purchase, so the two can never drift into showing different totals or a
different number.
"""

import logging

from django.utils import timezone

from .invoice_pdf import (
    COMPANY_BANK_ACCOUNT_NO,
    COMPANY_BANK_NAME,
    COMPANY_EMAIL,
    COMPANY_NAME,
    ensure_invoice_pdf,
    tax_line_items,
)

logger = logging.getLogger(__name__)


def email_invoice(invoice) -> dict:
    """Send `invoice` to the seller's registered address and stamp
    `emailed_at`. Returns the send result: {'sent': bool, 'error': str|None}."""
    from customerapp.email_otp import send_invoice_email

    seller = invoice.seller
    if not (seller.email or '').strip():
        return {'sent': False, 'error': 'This seller has no email on file.'}

    # Permanent, unauthenticated /media/ link — unlike the signed download_url
    # used in the admin panel, an emailed link needs to keep working whenever
    # the recipient eventually opens the email.
    download_url = ensure_invoice_pdf(invoice)

    result = send_invoice_email(
        to_email=seller.email,
        business_name=seller.business_name,
        invoice_number=invoice.display_number,
        amount=invoice.amount,
        tax_lines=tax_line_items(invoice),
        total_amount=invoice.amount + invoice.tax_amount,
        status_label=invoice.get_status_display(),
        plan_name=invoice.plan_label,
        period_start=invoice.period_start.strftime('%d %b %Y'),
        period_end=invoice.period_end.strftime('%d %b %Y'),
        payment_method_label=invoice.get_payment_method_display(),
        offline_reference=invoice.offline_reference or None,
        download_url=download_url,
        bank_name=COMPANY_BANK_NAME,
        bank_account_no=COMPANY_BANK_ACCOUNT_NO,
        support_email=COMPANY_EMAIL,
        company_name=COMPANY_NAME,
    )

    if result.get('sent'):
        invoice.emailed_at = timezone.now()
        invoice.save(update_fields=['emailed_at'])

    return result
