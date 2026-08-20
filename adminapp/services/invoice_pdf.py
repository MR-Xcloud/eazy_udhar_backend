from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

PUBLIC_STATEMENT_BASE_URL = getattr(settings, 'PUBLIC_STATEMENT_BASE_URL', '') or ''

LOGO_PATH = Path(settings.BASE_DIR) / 'adminapp' / 'assets' / 'eazyudhar-logo.png'

COMPANY_NAME = 'INWIZY GLOBAL VENTURES LLP'
COMPANY_ADDRESS_LINES = [
    'Workpod Seat No-31',
    'Plot No-93, 4th floor',
    'Sector -44, Gurgaon - 122003',
    'Haryana, INDIA',
]
COMPANY_GST_NUMBER = '06AALFI7026D1ZJ'
COMPANY_BANK_NAME = 'AU Small Finance Bank'
COMPANY_BANK_ACCOUNT_NO = '2502244382927932'
COMPANY_EMAIL = 'support@eazyudhar.com'


def _invoices_dir() -> Path:
    path = Path(settings.MEDIA_ROOT) / 'invoices'
    path.mkdir(parents=True, exist_ok=True)
    return path


# The file name stays on the local `invoice_number`: CRM numbers carry slashes
# (IGVL/INV/2026-27/00002) and cannot be a path segment. Only the number printed
# inside the document follows `display_number`.
def invoice_pdf_path(invoice) -> Path:
    return _invoices_dir() / f'{invoice.invoice_number}.pdf'


def invoice_pdf_url(invoice) -> str:
    base = PUBLIC_STATEMENT_BASE_URL.rstrip('/')
    return f'{base}/media/invoices/{invoice.invoice_number}.pdf'


def tax_line_items(invoice) -> list:
    """GST breakdown as [{'label', 'amount'}, ...] — CGST+SGST split or a
    single IGST line, matching `invoice.tax_type`. Shared by the PDF and the
    invoice email so both always show the same breakdown."""
    if not invoice.tax_amount:
        return []
    gst_rate = round((invoice.tax_amount / invoice.amount) * 100) if invoice.amount else 0
    if invoice.tax_type == invoice.TAX_TYPE_IGST:
        return [{'label': f'IGST @ {gst_rate}%', 'amount': invoice.tax_amount}]
    half_rate = gst_rate / 2
    half_amount = invoice.tax_amount / 2
    return [
        {'label': f'CGST @ {half_rate:g}%', 'amount': half_amount},
        {'label': f'SGST @ {half_rate:g}%', 'amount': half_amount},
    ]


def generate_invoice_pdf(invoice) -> Path:
    """Render `invoice` to a PDF on disk and return its path. Overwrites any
    existing file for this invoice number (e.g. on regeneration)."""
    seller = invoice.seller
    total = invoice.amount + invoice.tax_amount

    out_path = invoice_pdf_path(invoice)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=invoice.display_number,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'InvoiceTitle', parent=styles['Title'], alignment=2, fontSize=20, spaceAfter=0,
    )
    heading = ParagraphStyle('Heading', parent=styles['Normal'], fontSize=11, spaceAfter=4, leading=14)

    story = []

    company_style = ParagraphStyle('Company', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.grey)
    logo_cell = Image(str(LOGO_PATH), width=40 * mm, height=(40 * mm * 1024 / 1536)) if LOGO_PATH.exists() else Paragraph('<b>EazyUdhar</b>', styles['Normal'])
    company_lines = [f'<b>{COMPANY_NAME}</b>'] + COMPANY_ADDRESS_LINES + [
        f'GSTIN: {COMPANY_GST_NUMBER}',
        COMPANY_EMAIL,
    ]

    header_table = Table(
        [[
            logo_cell,
            Paragraph(f'<b>INVOICE</b><br/>{invoice.display_number}', title_style),
        ]],
        colWidths=[90 * mm, 70 * mm],
    )
    header_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('<br/>'.join(company_lines), company_style))
    story.append(Spacer(1, 8 * mm))

    status_label = invoice.get_status_display()
    method_label = invoice.get_payment_method_display()
    meta_rows = [
        ['Invoice date', invoice.created_at.strftime('%d %b %Y')],
    ]
    # An SMS pack is a one-off top-up with no period to state; subscriptions and
    # the time-limited Excel add-on both bill for a window.
    if invoice.period_end > invoice.period_start:
        meta_rows.append([
            'Billing period' if invoice.kind == invoice.KIND_SUBSCRIPTION else 'Access period',
            f'{invoice.period_start:%d %b %Y} – {invoice.period_end:%d %b %Y}',
        ])
    meta_rows += [
        ['Status', status_label],
        ['Payment method', method_label],
    ]
    if invoice.payment_method == invoice.PAYMENT_METHOD_OFFLINE:
        if invoice.offline_reference:
            meta_rows.append(['UPI/Txn reference', invoice.offline_reference])
        if invoice.paid_at:
            meta_rows.append(['Paid on', invoice.paid_at.strftime('%d %b %Y %H:%M')])
        if invoice.recorded_by_id:
            meta_rows.append(['Recorded by', invoice.recorded_by.full_name])

    bill_to_lines = [f'<b>{seller.business_name}</b>']
    if seller.full_name and seller.full_name != seller.business_name:
        bill_to_lines.append(seller.full_name)
    if seller.address:
        bill_to_lines.append(seller.address.replace('\n', '<br/>'))
    bill_to_lines.append(f'GSTIN: {seller.gst_number or "N/A"}')
    bill_to_lines.append(seller.email)
    bill_to_lines.append(f'Phone: {seller.phone or "N/A"}')

    info_table = Table(
        [[
            Paragraph('<br/>'.join(bill_to_lines), heading),
            Table(meta_rows, colWidths=[35 * mm, 45 * mm], style=TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
            ])),
        ]],
        colWidths=[90 * mm, 70 * mm],
    )
    info_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(info_table)
    story.append(Spacer(1, 10 * mm))

    line_rows = [
        ['Description', 'Amount'],
        [invoice.line_description, f'Rs. {invoice.amount:,.2f}'],
    ]
    for line in tax_line_items(invoice):
        line_rows.append([line['label'], f"Rs. {line['amount']:,.2f}"])
    line_rows.append(['Total', f'Rs. {total:,.2f}'])

    items_table = Table(line_rows, colWidths=[130 * mm, 30 * mm])
    items_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.75, colors.black),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12 * mm))

    if invoice.notes:
        story.append(Paragraph(f'<b>Notes:</b> {invoice.notes}', styles['Normal']))
        story.append(Spacer(1, 6 * mm))

    bank_lines = [
        '<b>Bank details for payment</b>',
        f'Bank Name: {COMPANY_BANK_NAME}',
        f'Account No: {COMPANY_BANK_ACCOUNT_NO}',
        f'Support: {COMPANY_EMAIL}',
    ]
    story.append(Paragraph('<br/>'.join(bank_lines), ParagraphStyle(
        'Bank', parent=styles['Normal'], fontSize=9, leading=13,
    )))
    story.append(Spacer(1, 8 * mm))

    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, leading=11)
    story.append(Paragraph(
        f'EazyUdhar is a brand owned and operated by {COMPANY_NAME}.',
        footer_style,
    ))
    story.append(Paragraph(
        'This is a system-generated invoice.',
        footer_style,
    ))

    doc.build(story)
    return out_path


def write_invoice_pdf(invoice) -> Path:
    """Put the invoice's PDF on disk and return its path.

    CRM finance is the book of record, so once an invoice is booked there its
    document is CRM's — fetched and cached here, INWIZY letterhead and all, so
    the admin panel, the emailed /media/ link and the CRM ledger all hand out
    one identical file. The local ReportLab rendering is the fallback for
    invoices that have not reached CRM (a draft, or a sync still pending)."""
    from .crm_invoice_pdf import fetch_crm_invoice_pdf

    data = fetch_crm_invoice_pdf(invoice)
    if data:
        out_path = invoice_pdf_path(invoice)
        out_path.write_bytes(data)
        return out_path
    return generate_invoice_pdf(invoice)


def _is_stale(invoice, path) -> bool:
    """True when the cached file predates the CRM sync — i.e. it is the local
    rendering with the local number, written before CRM had booked the invoice.
    Without this, an invoice that synced after its PDF was made would keep
    serving the superseded document forever."""
    if not invoice.crm_invoice_no or not invoice.crm_synced_at:
        return False
    return path.stat().st_mtime < invoice.crm_synced_at.timestamp()


def ensure_invoice_pdf(invoice, *, refresh=False) -> str:
    """Write the PDF if missing, stale or `refresh`, and return the public URL,
    persisting it onto `invoice.pdf_url` if it changed."""
    path = invoice_pdf_path(invoice)
    if refresh or not path.exists() or _is_stale(invoice, path):
        write_invoice_pdf(invoice)
    url = invoice_pdf_url(invoice)
    if invoice.pdf_url != url:
        invoice.pdf_url = url
        invoice.save(update_fields=['pdf_url'])
    return url
