import logging
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings

from customerapp.messaging import normalize_phone

logger = logging.getLogger(__name__)


def _sms_print(message):
    print(f'[EasyUdhar SMS] {message}', flush=True)


def nimbus_sms_configured():
    return bool(
        settings.NIMBUS_SMS_ENABLED
        and settings.NIMBUS_USER_ID
        and settings.NIMBUS_AUTH_KEY
        and settings.NIMBUS_SENDER_ID
        and settings.NIMBUS_DLT_ENTITY_ID
        and settings.NIMBUS_API_URL
    )


def _format_amount(amount):
    value = Decimal(str(amount))
    if value == value.to_integral_value():
        return str(int(value))
    return str(value)


def _format_template_value(value, *, max_len=None):
    text = str(value or '').strip()
    if max_len is None:
        max_len = getattr(settings, 'NIMBUS_SMS_VAR_MAX_LENGTH', 30)
    if max_len > 0 and len(text) > max_len:
        return text[:max_len]
    return text


def _format_mobile_for_api(phone):
    """Return mobile string for Nimbus API (10-digit or with country prefix)."""
    prefix = getattr(settings, 'NIMBUS_MOBILE_PREFIX', '').strip()
    if prefix:
        return f'{prefix}{phone}'
    return phone


def _apply_template(template, values, *, raw_var_indices=None):
    """Replace {#var#} placeholders; raw_var_indices skips truncation (e.g. statement URL)."""
    raw_var_indices = raw_var_indices or set()
    text = template
    for index, value in enumerate(values):
        if index in raw_var_indices:
            replacement = _format_template_value(
                value,
                max_len=getattr(settings, 'NIMBUS_SMS_LINK_VAR_MAX_LENGTH', 0),
            )
        else:
            replacement = _format_template_value(value)
        text = text.replace('{#var#}', replacement, 1)
    return text


def _build_credit_text(amount, shop_name):
    """CREDIT3: amount, added-by shop, platform name."""
    return _apply_template(
        settings.NIMBUS_CREDIT_SMS_TEXT,
        [
            _format_amount(amount),
            shop_name,
            settings.NIMBUS_SMS_PLATFORM_NAME,
        ],
    )


def _build_payment_text(amount, shop_name):
    """PAYMENT3: amount, credited-by shop, platform name."""
    return _apply_template(
        settings.NIMBUS_PAYMENT_SMS_TEXT,
        [
            _format_amount(amount),
            shop_name,
            settings.NIMBUS_SMS_PLATFORM_NAME,
        ],
    )


def send_push_sms(*, mobile, text, template_id):
    """
    Call Nimbus pushsms API (GET).
    Returns dict: {sent, message_id, error, raw_response}
    """
    phone = normalize_phone(mobile)
    if len(phone) != 10:
        _sms_print(f'SKIPPED — invalid phone: {mobile!r} (normalized: {phone!r})')
        return {
            'sent': False,
            'message_id': '',
            'error': 'Invalid customer phone number.',
            'raw_response': '',
        }

    if not nimbus_sms_configured():
        missing = []
        if not settings.NIMBUS_DLT_ENTITY_ID:
            missing.append('NIMBUS_DLT_ENTITY_ID')
        if not settings.NIMBUS_USER_ID:
            missing.append('NIMBUS_USER_ID')
        if not settings.NIMBUS_AUTH_KEY:
            missing.append('NIMBUS_AUTH_KEY')
        err = 'Nimbus SMS not configured' + (
            f' (missing: {", ".join(missing)})' if missing else '.'
        )
        _sms_print(f'SKIPPED — {err}')
        return {
            'sent': False,
            'message_id': '',
            'error': err,
            'raw_response': '',
        }

    _sms_print(f'Sending to {phone} | template={template_id}')
    _sms_print(f'Message: {text}')

    api_mobile = _format_mobile_for_api(phone)
    if api_mobile != phone:
        _sms_print(f'API mobile (with prefix): {api_mobile}')

    params = {
        'user': settings.NIMBUS_USER_ID,
        'authkey': settings.NIMBUS_AUTH_KEY,
        'sender': settings.NIMBUS_SENDER_ID,
        'mobile': api_mobile,
        'text': text,
        'entityid': settings.NIMBUS_DLT_ENTITY_ID,
        'templateid': template_id,
        'rpt': '1',
    }
    if settings.NIMBUS_PASSWORD:
        params['password'] = settings.NIMBUS_PASSWORD

    category = getattr(settings, 'NIMBUS_SMS_CATEGORY', '').strip()
    sub_category = getattr(settings, 'NIMBUS_SMS_SUB_CATEGORY', '').strip()
    if category:
        params['category'] = category
    if sub_category:
        params['subcategory'] = sub_category
        params['sub_category'] = sub_category

    extra_raw = getattr(settings, 'NIMBUS_SMS_EXTRA_PARAMS', '').strip()
    if extra_raw:
        for part in extra_raw.split('&'):
            if '=' in part:
                key, value = part.split('=', 1)
                params[key.strip()] = value.strip()

    _sms_print(
        f'Route: category={category or "-"} sub_category={sub_category or "-"} sender={settings.NIMBUS_SENDER_ID}'
    )
    url = f'{settings.NIMBUS_API_URL.rstrip("/")}?{urlencode(params)}'

    try:
        with urlopen(url, timeout=settings.NIMBUS_REQUEST_TIMEOUT) as response:
            body = response.read().decode('utf-8', errors='replace').strip()
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace').strip()
        logger.warning('Nimbus SMS HTTP error: %s %s', exc.code, body)
        _sms_print(f'FAILED — HTTP {exc.code}: {body}')
        return {
            'sent': False,
            'message_id': '',
            'error': body or str(exc),
            'raw_response': body,
        }
    except URLError as exc:
        logger.warning('Nimbus SMS network error: %s', exc)
        _sms_print(f'FAILED — network error: {exc.reason or exc}')
        return {
            'sent': False,
            'message_id': '',
            'error': str(exc.reason or exc),
            'raw_response': '',
        }

    sent = _response_indicates_success(body)
    result = {
        'sent': sent,
        'message_id': body if sent else '',
        'error': '' if sent else body or 'SMS send failed',
        'raw_response': body,
    }
    if sent:
        logger.info('Nimbus SMS submitted to %s template=%s', phone, template_id)
        _sms_print(f'QUEUED — accepted by Nimbus API for {api_mobile} (check portal report for DELIVERED/FAILED)')
        _sms_print(f'Nimbus response: {body}')
    else:
        logger.warning('Nimbus SMS failed to %s: %s', phone, body)
        _sms_print(f'FAILED — Nimbus response: {body}')
    return result


def _response_indicates_success(body):
    lowered = (body or '').lower()
    if not lowered:
        return False
    if '"status":"ok"' in lowered or '"code":"100"' in lowered:
        return True
    failure_markers = ('"fail"', ' rejected', 'invalid', 'denied', 'not allowed')
    if any(marker in lowered for marker in failure_markers):
        return False
    success_markers = ('success', 'submitted', 'submit', 'queued', 'messageid', 'msgid')
    if any(marker in lowered for marker in success_markers):
        return True
    return body.replace('-', '').replace('{', '').isdigit()


def send_reminder_sms(*, seller, customer, message):
    _sms_print(
        f'REMINDER SMS — customer={customer.name!r} phone={customer.phone!r} '
        f'shop={seller.business_name!r}'
    )
    template_id = getattr(settings, 'NIMBUS_REMINDER_TEMPLATE_ID', '').strip()
    if not template_id:
        return {
            'sent': False,
            'message_id': '',
            'error': 'Reminder SMS template not configured (NIMBUS_REMINDER_TEMPLATE_ID).',
            'raw_response': '',
        }
    text = _apply_template(
        getattr(
            settings,
            'NIMBUS_REMINDER_SMS_TEXT',
            'Reminder: Rs. {#var#} outstanding at {#var#}. Dear {#var#}, please pay. - EAZYUDHAR',
        ),
        [
            _format_amount(customer.outstanding_amount),
            seller.business_name,
            customer.name,
        ],
    )
    return send_push_sms(
        mobile=customer.phone,
        text=text,
        template_id=template_id,
    )


def send_summary_sms(*, seller, text):
    _sms_print(f'SUMMARY SMS — seller={seller.business_name!r}')
    template_id = getattr(settings, 'NIMBUS_SUMMARY_TEMPLATE_ID', '').strip()
    if not template_id:
        return {
            'sent': False,
            'message_id': '',
            'error': 'Summary SMS template not configured (NIMBUS_SUMMARY_TEMPLATE_ID).',
            'raw_response': '',
        }
    return send_push_sms(
        mobile=seller.phone,
        text=text[:500],
        template_id=template_id,
    )


def send_credit_sms(*, seller, customer, amount, balance=None):
    _sms_print(
        f'CREDIT SMS — customer={customer.name!r} phone={customer.phone!r} '
        f'amount={amount} shop={seller.business_name!r}'
    )
    text = _build_credit_text(amount, seller.business_name)
    return send_push_sms(
        mobile=customer.phone,
        text=text,
        template_id=settings.NIMBUS_CREDIT_TEMPLATE_ID,
    )


def send_payment_sms(*, seller, customer, amount, balance=None, payment_method=''):
    _sms_print(
        f'PAYMENT SMS — customer={customer.name!r} phone={customer.phone!r} '
        f'amount={amount} shop={seller.business_name!r} method={payment_method!r}'
    )
    text = _build_payment_text(amount, seller.business_name)
    return send_push_sms(
        mobile=customer.phone,
        text=text,
        template_id=settings.NIMBUS_PAYMENT_TEMPLATE_ID,
    )


def _build_daily_credit_text(amount, shop_name, statement_url):
    """Nightly digest — third {#var#} is the customer's day-statement link."""
    return _apply_template(
        settings.NIMBUS_CREDIT_SMS_TEXT,
        [
            _format_amount(amount),
            shop_name,
            statement_url,
        ],
        raw_var_indices={2},
    )


def _build_daily_payment_text(amount, shop_name, statement_url):
    """Nightly digest — third {#var#} is the customer's day-statement link."""
    return _apply_template(
        settings.NIMBUS_PAYMENT_SMS_TEXT,
        [
            _format_amount(amount),
            shop_name,
            statement_url,
        ],
        raw_var_indices={2},
    )


def _build_otp_text(otp):
    return _apply_template(
        settings.NIMBUS_OTP_SMS_TEXT,
        [otp],
    )


def send_otp_sms(*, mobile, otp):
    _sms_print(f'OTP SMS — mobile={mobile!r} otp={otp}')
    text = _build_otp_text(otp)
    return send_push_sms(
        mobile=mobile,
        text=text,
        template_id=settings.NIMBUS_OTP_TEMPLATE_ID,
    )


def send_daily_digest_sms(*, seller, customer, digest):
    """
    One SMS per customer per night summarizing the day's credit/payment activity.
    Uses CREDIT template if any credit today, else PAYMENT template.
    """
    from .daily_sms import statement_link

    link = statement_link(digest.token)
    shop_name = seller.business_name
    has_credit = digest.credit_total > 0
    has_payment = digest.payment_total > 0

    if has_credit:
        amount = digest.credit_total
        text = _build_daily_credit_text(amount, shop_name, link)
        template_id = settings.NIMBUS_CREDIT_TEMPLATE_ID
        kind = 'CREDIT DIGEST'
    elif has_payment:
        amount = digest.payment_total
        text = _build_daily_payment_text(amount, shop_name, link)
        template_id = settings.NIMBUS_PAYMENT_TEMPLATE_ID
        kind = 'PAYMENT DIGEST'
    else:
        return {
            'sent': False,
            'message_id': '',
            'error': 'No credit or payment activity for digest',
            'raw_response': '',
        }

    _sms_print(
        f'{kind} SMS — customer={customer.name!r} phone={customer.phone!r} '
        f'amount={amount} date={digest.activity_date} link={link!r}'
    )
    return send_push_sms(
        mobile=customer.phone,
        text=text,
        template_id=template_id,
    )
