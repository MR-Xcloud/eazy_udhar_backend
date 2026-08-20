"""Outbound side of the Telegram support bot — sending replies via the Bot API."""

import requests
from django.conf import settings


class TelegramSendError(Exception):
    pass


def send_telegram_message(chat_id, text, message_thread_id=None):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise TelegramSendError('TELEGRAM_BOT_TOKEN is not configured.')

    body = {'chat_id': chat_id, 'text': text}
    if message_thread_id is not None:
        # Chats with Topics enabled file replies under "General" unless the
        # reply is addressed to the same thread the customer is looking at.
        body['message_thread_id'] = message_thread_id

    response = requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        json=body,
        timeout=10,
    )
    payload = response.json()
    if not payload.get('ok'):
        raise TelegramSendError(payload.get('description', 'Telegram API rejected the message.'))
    return payload['result']
