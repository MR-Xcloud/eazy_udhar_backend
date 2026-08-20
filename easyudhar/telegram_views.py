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

# Telegram sends these as ordinary `message` updates with no text/caption —
# e.g. a customer's client auto-creating a "topic" the first time they message
# the bot. They're not customer content, so don't store or alert on them.
SERVICE_MESSAGE_KEYS = {
    'forum_topic_created', 'forum_topic_edited', 'forum_topic_closed', 'forum_topic_reopened',
    'general_forum_topic_hidden', 'general_forum_topic_unhidden',
    'pinned_message', 'new_chat_members', 'left_chat_member', 'new_chat_title',
    'new_chat_photo', 'delete_chat_photo', 'group_chat_created', 'supergroup_chat_created',
    'channel_chat_created', 'migrate_to_chat_id', 'migrate_from_chat_id',
    'message_auto_delete_timer_changed', 'video_chat_scheduled', 'video_chat_started',
    'video_chat_ended', 'video_chat_participants_invited', 'web_app_data',
    'proximity_alert_triggered',
}


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
        if message and SERVICE_MESSAGE_KEYS.intersection(message) and not message.get('text'):
            message = None
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
                telegram_message_id=message.get('message_id'),
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
                telegram_chat_id=chat_id,
            )

        # Telegram only cares about the 200 — body is ignored.
        return Response(status=status.HTTP_200_OK)
