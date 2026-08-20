from django.db.models import Count, Max
from rest_framework import status
from rest_framework.response import Response

from ..models import TelegramChatLink, TelegramMessage
from ..services.telegram import TelegramSendError, send_telegram_message
from ..utils import log_audit
from .base import AdminAPIView


def _telegram_message_item(msg, seller=None):
    return {
        'id': msg.id,
        'chat_id': msg.chat_id,
        'telegram_user_id': msg.telegram_user_id,
        'username': msg.username,
        'first_name': msg.first_name,
        'last_name': msg.last_name,
        'text': msg.text,
        'direction': msg.direction,
        'created_at': msg.created_at.isoformat(),
        'seller_id': seller.id if seller else None,
        'seller_name': seller.business_name if seller else None,
        'seller_phone': seller.phone if seller else None,
    }


def _telegram_conversation_item(chat_id, message_count, seller):
    latest = TelegramMessage.objects.filter(chat_id=chat_id).order_by('-created_at').first()
    # Customer identity fields are blank on our own outbound rows, so pull
    # them from the most recent message the customer actually sent.
    identity_src = (
        TelegramMessage.objects.filter(chat_id=chat_id, direction=TelegramMessage.DIRECTION_IN)
        .order_by('-created_at')
        .first()
        or latest
    )
    return {
        'chat_id': chat_id,
        'telegram_user_id': identity_src.telegram_user_id if identity_src else None,
        'username': identity_src.username if identity_src else '',
        'first_name': identity_src.first_name if identity_src else '',
        'last_name': identity_src.last_name if identity_src else '',
        'last_message': latest.text if latest else '',
        'last_direction': latest.direction if latest else None,
        'last_message_at': latest.created_at.isoformat() if latest else None,
        'message_count': message_count,
        'seller_id': seller.id if seller else None,
        'seller_name': seller.business_name if seller else None,
        'seller_phone': seller.phone if seller else None,
    }


def _sellers_by_chat_id(chat_ids):
    links = TelegramChatLink.objects.filter(chat_id__in=chat_ids).select_related('seller')
    return {link.chat_id: link.seller for link in links}


class TelegramConversationListView(AdminAPIView):
    """One row per Telegram chat — the inbox view."""

    def get(self, request):
        qs = TelegramMessage.objects.all()
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(text__icontains=search)
        grouped = (
            qs.values('chat_id')
            .annotate(last_at=Max('created_at'), message_count=Count('id'))
            .order_by('-last_at')
        )
        page, paginator = self.paginate(request, grouped)
        chat_ids = [row['chat_id'] for row in page]
        sellers = _sellers_by_chat_id(chat_ids)
        counts = {row['chat_id']: row['message_count'] for row in page}
        data = [
            _telegram_conversation_item(chat_id, counts[chat_id], sellers.get(chat_id))
            for chat_id in chat_ids
        ]
        return paginator.get_paginated_response(data)


class TelegramMessageListView(AdminAPIView):
    def get(self, request):
        qs = TelegramMessage.objects.all().order_by('-created_at')
        chat_id = request.query_params.get('chat_id')
        if chat_id:
            qs = qs.filter(chat_id=chat_id)
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(text__icontains=search)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        page, paginator = self.paginate(request, qs)
        sellers = _sellers_by_chat_id({m.chat_id for m in page})
        data = [_telegram_message_item(m, sellers.get(m.chat_id)) for m in page]
        return paginator.get_paginated_response(data)


class TelegramMessageReplyView(AdminAPIView):
    def post(self, request):
        chat_id = request.data.get('chat_id')
        text = (request.data.get('text') or '').strip()
        if not chat_id or not text:
            return Response({'detail': 'chat_id and text are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            send_telegram_message(chat_id, text)
        except TelegramSendError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        msg = TelegramMessage.objects.create(
            chat_id=chat_id,
            text=text,
            direction=TelegramMessage.DIRECTION_OUT,
            sent_by=request.user,
        )
        log_audit(request.user, 'telegram_reply', 'telegram_message', msg.pk, request=request)
        seller = _sellers_by_chat_id([chat_id]).get(chat_id)
        return Response(_telegram_message_item(msg, seller), status=status.HTTP_201_CREATED)
