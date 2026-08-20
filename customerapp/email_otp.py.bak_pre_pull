import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.text import MIMEText

from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

BRAND_FOOTER = 'EAZYUDHAR by INWIZY'
INVOICE_BCC_EMAIL = 'admin@inwizy.com'


def postmark_configured():
    return bool(
        getattr(settings, 'POSTMARK_SERVER_TOKEN', '').strip()
        and settings.DEFAULT_FROM_EMAIL
    )


def _otp_subject():
    return getattr(settings, 'OTP_EMAIL_SUBJECT', 'Your EAZYUDHAR login code')


def _otp_context(otp):
    minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 5)
    return {
        'otp': otp,
        'expiry_minutes': minutes,
        'brand_footer': BRAND_FOOTER,
        'logo_url': getattr(settings, 'OTP_EMAIL_LOGO_URL', ''),
    }


def _otp_text_body(otp):
    minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 5)
    return (
        f'Your EAZYUDHAR login code\n\n'
        f'{otp}\n\n'
        f'This code is valid for {minutes} minutes.\n'
        f'Do not share it with anyone.\n\n'
        f'If you did not request this code, ignore this email.\n\n'
        f'{BRAND_FOOTER}'
    )


def _otp_html_body(otp):
    return render_to_string('emails/otp_login.html', _otp_context(otp))


def _send_via_postmark_api(*, to_email, subject, text_body, html_body, bcc_email=None):
    """Send a single email via Postmark HTTP API."""
    token = settings.POSTMARK_SERVER_TOKEN
    payload = {
        'From': settings.DEFAULT_FROM_EMAIL,
        'To': to_email,
        'Subject': subject,
        'TextBody': text_body,
        'HtmlBody': html_body,
        'MessageStream': getattr(settings, 'POSTMARK_MESSAGE_STREAM', 'outbound'),
    }
    if bcc_email:
        payload['Bcc'] = bcc_email
    req = urllib.request.Request(
        'https://api.postmarkapp.com/email',
        data=json.dumps(payload).encode(),
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Postmark-Server-Token': token,
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=settings.EMAIL_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def send_otp_email(*, to_email, otp):
    """Send one professional OTP email via Postmark API."""
    to_email = (to_email or '').strip().lower()
    if not to_email or '@' not in to_email:
        return {
            'sent': False,
            'channel': 'email',
            'error': 'Valid email address is required.',
            'from': settings.DEFAULT_FROM_EMAIL,
        }

    if not postmark_configured():
        return {
            'sent': False,
            'channel': 'email',
            'error': 'Email OTP not configured (POSTMARK_SERVER_TOKEN / OTP_FROM_EMAIL).',
            'from': settings.DEFAULT_FROM_EMAIL,
        }

    try:
        result = _send_via_postmark_api(
            to_email=to_email,
            subject=_otp_subject(),
            text_body=_otp_text_body(otp),
            html_body=_otp_html_body(otp),
        )
        logger.info(
            'OTP email sent to %s message_id=%s',
            to_email,
            result.get('MessageID'),
        )
        return {
            'sent': True,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'message_id': result.get('MessageID', ''),
            'error': '',
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors='replace')
        try:
            detail = json.loads(body).get('Message', body)
        except json.JSONDecodeError:
            detail = body
        logger.warning('OTP email failed to %s: %s', to_email, detail)
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'error': detail,
        }
    except Exception as exc:
        logger.warning('OTP email failed to %s: %s', to_email, exc)
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'error': str(exc),
        }


def send_password_reset_email(
    *,
    to_email,
    user_name,
    temp_password,
    account_label='app',
    product_name='EazyUdhar',
):
    """Email a temporary password after an admin-initiated reset."""
    to_email = (to_email or '').strip().lower()
    if not to_email or '@' not in to_email:
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'error': 'Valid email address is required.',
            'from': settings.DEFAULT_FROM_EMAIL,
        }

    if not postmark_configured():
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'error': 'Email not configured (POSTMARK_SERVER_TOKEN / OTP_FROM_EMAIL).',
            'from': settings.DEFAULT_FROM_EMAIL,
        }

    subject = f'Your {product_name} password was reset'
    context = {
        'user_name': user_name or 'there',
        'temp_password': temp_password,
        'account_label': account_label,
        'product_name': product_name,
        'brand_footer': BRAND_FOOTER,
        'logo_url': getattr(settings, 'OTP_EMAIL_LOGO_URL', ''),
    }
    text_body = (
        f'Hello {context["user_name"]},\n\n'
        f'An administrator reset your {product_name} password.\n\n'
        f'Temporary password: {temp_password}\n\n'
        f'Sign in to the {account_label} with your email and this password.\n\n'
        f'If you did not expect this email, contact support immediately.\n\n'
        f'{BRAND_FOOTER}'
    )
    html_body = render_to_string('emails/password_reset.html', context)

    try:
        result = _send_via_postmark_api(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
        logger.info(
            'Password reset email sent to %s message_id=%s',
            to_email,
            result.get('MessageID'),
        )
        return {
            'sent': True,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'message_id': result.get('MessageID', ''),
            'error': '',
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors='replace')
        try:
            detail = json.loads(body).get('Message', body)
        except json.JSONDecodeError:
            detail = body
        logger.warning('Password reset email failed to %s: %s', to_email, detail)
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'error': detail,
        }
    except Exception as exc:
        logger.warning('Password reset email failed to %s: %s', to_email, exc)
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'error': str(exc),
        }


def send_invoice_email(
    *,
    to_email,
    business_name,
    invoice_number,
    amount,
    tax_lines,
    total_amount,
    status_label,
    plan_name,
    period_start,
    period_end,
    payment_method_label,
    offline_reference,
    download_url,
    bank_name,
    bank_account_no,
    support_email,
    company_name,
    currency_symbol='Rs. ',
):
    """Email a branded invoice (matching the password-reset/OTP email style) to
    the seller's registered email, with a permanent link to the PDF."""
    to_email = (to_email or '').strip().lower()
    if not to_email or '@' not in to_email:
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'error': 'Valid email address is required.',
            'from': settings.DEFAULT_FROM_EMAIL,
        }

    if not postmark_configured():
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'error': 'Email not configured (POSTMARK_SERVER_TOKEN / OTP_FROM_EMAIL).',
            'from': settings.DEFAULT_FROM_EMAIL,
        }

    subject = f'Invoice {invoice_number} from EazyUdhar'
    text_lines = [
        f'Hello {business_name},',
        '',
        f'Invoice {invoice_number} — {plan_name} plan ({period_start} - {period_end})',
        f'{plan_name} subscription: {currency_symbol}{amount}',
    ]
    for line in tax_lines:
        text_lines.append(f"{line['label']}: {currency_symbol}{line['amount']}")
    text_lines += [
        f'Total: {currency_symbol}{total_amount} — {status_label}',
        '',
    ]
    if payment_method_label:
        ref = f" (ref: {offline_reference})" if offline_reference else ''
        text_lines.append(f'Payment method: {payment_method_label}{ref}')
        text_lines.append('')
    text_lines += [
        f'Download the invoice PDF: {download_url}',
        '',
        f'Bank details: {bank_name}, A/C {bank_account_no}',
        f'Questions: {support_email}',
        '',
        BRAND_FOOTER,
    ]
    text_body = '\n'.join(text_lines)

    status_colors = {
        'Paid': ('#d1fae5', '#065f46'),
        'Draft': ('#e2e8f0', '#334155'),
        'Void': ('#fee2e2', '#991b1b'),
    }
    status_bg, status_fg = status_colors.get(status_label, ('#e2e8f0', '#334155'))

    html_body = render_to_string('emails/invoice.html', {
        'business_name': business_name,
        'invoice_number': invoice_number,
        'amount': amount,
        'tax_lines': tax_lines,
        'total_amount': total_amount,
        'currency_symbol': currency_symbol,
        'status_label': status_label,
        'status_bg': status_bg,
        'status_fg': status_fg,
        'plan_name': plan_name,
        'period_start': period_start,
        'period_end': period_end,
        'payment_method_label': payment_method_label,
        'offline_reference': offline_reference,
        'download_url': download_url,
        'bank_name': bank_name,
        'bank_account_no': bank_account_no,
        'support_email': support_email,
        'company_name': company_name,
        'logo_url': getattr(settings, 'OTP_EMAIL_LOGO_URL', ''),
    })

    try:
        result = _send_via_postmark_api(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            bcc_email=INVOICE_BCC_EMAIL if to_email != INVOICE_BCC_EMAIL.lower() else None,
        )
        logger.info(
            'Invoice email sent to %s message_id=%s',
            to_email,
            result.get('MessageID'),
        )
        return {
            'sent': True,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'message_id': result.get('MessageID', ''),
            'error': '',
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors='replace')
        try:
            detail = json.loads(body).get('Message', body)
        except json.JSONDecodeError:
            detail = body
        logger.warning('Invoice email failed to %s: %s', to_email, detail)
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'error': detail,
        }
    except Exception as exc:
        logger.warning('Invoice email failed to %s: %s', to_email, exc)
        return {
            'sent': False,
            'channel': 'email',
            'to': to_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'error': str(exc),
        }


def test_smtp_port(*, host, port, username, password, use_tls, use_ssl, from_email, to_email):
    """Raw SMTP test for a single port (used by management command)."""
    message = MIMEText('EAZYUDHAR Postmark SMTP connectivity test.')
    message['Subject'] = 'EAZYUDHAR SMTP test'
    message['From'] = from_email
    message['To'] = to_email

    if use_ssl:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    try:
        server.ehlo()
        if use_tls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(username, password)
        server.sendmail(from_email, [to_email], message.as_string())
        return {'port': port, 'sent': True, 'error': ''}
    except Exception as exc:
        return {'port': port, 'sent': False, 'error': str(exc)}
    finally:
        try:
            server.quit()
        except Exception:
            pass
