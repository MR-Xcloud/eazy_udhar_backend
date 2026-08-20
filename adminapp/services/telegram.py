"""Outbound side of the Telegram support bot — sending replies via the Bot API."""

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Connect fast, but give Telegram room to answer a slow send before we give up.
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15

# One pooled session for the whole process: a fresh TLS handshake to
# api.telegram.org costs ~110ms per call, which is most of a reply's latency.
# Retries cover the transient failures that used to surface as a reply hanging
# in "Sending…" — Telegram's 429 flood limit carries Retry-After, which urllib3
# honours here, so a rate-limited reply waits and lands instead of erroring.
_RETRY = Retry(
    total=2,
    connect=2,
    read=2,
    status=2,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({'POST'}),
    backoff_factor=0.5,
    respect_retry_after_header=True,
    raise_on_status=False,
)

_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=_RETRY)
_session.mount('https://', _adapter)


class TelegramSendError(Exception):
    pass


def _api_post(method, body):
    """POST to the Bot API, turning every failure into TelegramSendError.

    Callers translate that into a 502 with a readable message; letting a raw
    requests/JSON error escape would surface as an opaque 500 in the panel.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise TelegramSendError('TELEGRAM_BOT_TOKEN is not configured.')

    try:
        response = _session.post(
            f'https://api.telegram.org/bot{token}/{method}',
            json=body,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    except requests.Timeout:
        raise TelegramSendError('Telegram did not respond in time. The message was not sent.')
    except requests.RequestException as exc:
        raise TelegramSendError(f'Could not reach Telegram: {exc}')

    try:
        payload = response.json()
    except ValueError:
        raise TelegramSendError(f'Telegram returned an unreadable response (HTTP {response.status_code}).')

    if not payload.get('ok'):
        raise TelegramSendError(payload.get('description', 'Telegram API rejected the message.'))
    return payload['result']


def send_telegram_message(chat_id, text, message_thread_id=None):
    body = {'chat_id': chat_id, 'text': text}
    if message_thread_id is not None:
        # Chats with Topics enabled file replies under "General" unless the
        # reply is addressed to the same thread the customer is looking at.
        body['message_thread_id'] = message_thread_id

    return _api_post('sendMessage', body)


def delete_telegram_messages(chat_id, message_ids):
    """Best-effort bulk delete on Telegram's side. Old messages (>48h) or
    already-deleted ones are silently skipped — callers should still remove
    their own local records regardless of what Telegram reports here.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    ids = list(message_ids)
    if not token or not ids:
        return 0, len(ids)

    deleted = 0
    failed = 0
    for i in range(0, len(ids), 100):
        batch = ids[i : i + 100]
        try:
            response = _session.post(
                f'https://api.telegram.org/bot{token}/deleteMessages',
                json={'chat_id': chat_id, 'message_ids': batch},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            ok = response.json().get('ok')
        except (requests.RequestException, ValueError):
            ok = False
        if ok:
            deleted += len(batch)
        else:
            failed += len(batch)
    return deleted, failed
