"""WhatsApp reminder delivery (Meta Cloud API when configured)."""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from customerapp.messaging import normalize_phone

logger = logging.getLogger(__name__)


def whatsapp_configured():
    return bool(
        getattr(settings, 'WHATSAPP_API_ENABLED', False)
        and getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '').strip()
        and getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '').strip()
    )


def send_whatsapp_reminder(*, seller, customer, message):
    phone = normalize_phone(customer.phone)
    if len(phone) != 10:
        return {
            'sent': False,
            'channel': 'whatsapp',
            'error': 'Invalid customer phone number.',
        }

    if not whatsapp_configured():
        return {
            'sent': False,
            'channel': 'whatsapp',
            'error': (
                'WhatsApp API not configured. Set WHATSAPP_API_ENABLED=true, '
                'WHATSAPP_ACCESS_TOKEN, and WHATSAPP_PHONE_NUMBER_ID.'
            ),
        }

    token = settings.WHATSAPP_ACCESS_TOKEN.strip()
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID.strip()
    api_version = getattr(settings, 'WHATSAPP_API_VERSION', 'v21.0')
    url = f'https://graph.facebook.com/{api_version}/{phone_number_id}/messages'

    payload = {
        'messaging_product': 'whatsapp',
        'to': f'91{phone}',
        'type': 'text',
        'text': {'body': message[:4096]},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        logger.info('WhatsApp reminder sent to %s: %s', phone, body.get('messages'))
        return {'sent': True, 'channel': 'whatsapp', 'error': '', 'raw': body}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors='replace')
        logger.warning('WhatsApp API error: %s %s', exc.code, detail)
        return {'sent': False, 'channel': 'whatsapp', 'error': detail or str(exc)}
    except Exception as exc:
        logger.warning('WhatsApp send failed: %s', exc)
        return {'sent': False, 'channel': 'whatsapp', 'error': str(exc)}
