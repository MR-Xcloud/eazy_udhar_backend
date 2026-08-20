"""Telegram Bot API webhook — receives incoming messages sent to eazyudhar_bot."""

import hmac

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from adminapp.models import AdminAlert, TelegramChatLink, TelegramMessage
from easyudhar.telegram_link import verify_start_payload
from sellerapp.models import Seller


class TelegramWebhookView(APIView):
    """POST target registered with Telegram's setWebhook.

    The secret path segment must match TELEGRAM_WEBHOOK_SECRET — Telegram echoes
    the URL back verbatim on every update, so a wrong/missing secret is rejected
    as 404 rather than processed.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, secret):
        expected = settings.TELEGRAM_WEBHOOK_SECRET or ''
        if not expected or not hmac.compare_digest(secret, expected):
            return Response(status=status.HTTP_404_NOT_FOUND)

        update = request.data or {}
        message = update.get('message') or update.get('edited_message')
        if message:
            chat = message.get('chat') or {}
            sender = message.get('from') or {}
            who = sender.get('username') or sender.get('first_name') or str(chat.get('id', ''))
            text = message.get('text', '')
            chat_id = chat.get('id')

            if text.startswith('/start'):
                seller_id = verify_start_payload(text[len('/start'):].strip())
                if seller_id and Seller.objects.filter(id=seller_id).exists():
                    TelegramChatLink.objects.update_or_create(
                        chat_id=chat_id, defaults={'seller_id': seller_id}
                    )

            TelegramMessage.objects.create(
                chat_id=chat_id,
                telegram_user_id=sender.get('id'),
                username=sender.get('username', ''),
                first_name=sender.get('first_name', ''),
                last_name=sender.get('last_name', ''),
                text=text,
                message_thread_id=message.get('message_thread_id'),
                raw_update=update,
            )
            AdminAlert.objects.create(
                type=AdminAlert.TYPE_TELEGRAM_MESSAGE,
                title=f'Telegram message from {who}',
                body=text or '(non-text message)',
            )

        # Telegram only cares about the 200 — body is ignored.
        return Response(status=status.HTTP_200_OK)
