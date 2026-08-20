"""Fetch the finished invoice PDF back from the CRM finance module.

Once an invoice is booked in CRM, CRM's rendering is the document of record —
INWIZY letterhead, CRM's number, CRM's GST table. EazyUdhar serves that same
file rather than a look-alike, so what the seller downloads is exactly what the
ledger holds. The local ReportLab renderer stays as the fallback for invoices
that have not reached CRM (drafts, or a sync that has not landed yet).

Kept apart from `crm_invoice_sync` so `invoice_pdf` can import it without the
two forming an import cycle.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20


def fetch_crm_invoice_pdf(invoice):
    """CRM's PDF bytes for `invoice`, or None if it isn't there to fetch."""
    if not invoice.crm_invoice_no:
        return None

    url = (getattr(settings, 'CRM_API_URL', '') or '').rstrip('/')
    token = getattr(settings, 'CRM_API_TOKEN', '') or ''
    if not url or not token:
        return None

    try:
        response = requests.get(
            f'{url}/api/internal/invoices/pdf',
            params={'source': 'eazyudhar', 'reference_no': invoice.invoice_number},
            headers={'X-Internal-Token': token},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.error('CRM invoice PDF fetch threw for %s: %s', invoice.invoice_number, exc)
        return None

    if response.status_code != 200:
        logger.error(
            'CRM invoice PDF fetch failed for %s: HTTP %s %s',
            invoice.invoice_number, response.status_code, response.text[:300],
        )
        return None

    if not response.content.startswith(b'%PDF'):
        logger.error('CRM invoice PDF fetch returned non-PDF for %s', invoice.invoice_number)
        return None

    return response.content
