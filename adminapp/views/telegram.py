from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from ..models import AdminAlert, AuditLog, TelegramChatLink, TelegramMessage
from ..services.telegram import TelegramSendError, delete_telegram_messages, send_telegram_message
from ..utils import log_audit
from .base import AdminAPIView


def _tick_state(msg, seen_before=None):
    """Delivery/read state shown as ticks in the panel.

    Telegram's Bot API has no read receipt for bot messages, so 'read' on an
    outbound message is inferred: the customer wrote back after it, which means
    they had the chat open. `seen_before` is the newest incoming timestamp in
    the chat; anything we sent at or before it counts as seen.
    """
    if msg.direction == TelegramMessage.DIRECTION_IN:
        return 'read' if msg.read_at else 'unread'
    if not msg.telegram_message_id:
        return 'failed'
    if seen_before and msg.created_at <= seen_before:
        return 'read'
    # Telegram accepted and handed it to the customer's client.
    return 'delivered'


def _telegram_message_item(msg, seller=None, seen_before=None):
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
        'read_at': msg.read_at.isoformat() if msg.read_at else None,
        'tick': _tick_state(msg, seen_before),
        'seller_id': seller.id if seller else None,
        'seller_name': seller.business_name if seller else None,
        'seller_phone': seller.phone if seller else None,
    }


def _seen_before(chat_id):
    """Newest incoming timestamp in a chat — the 'customer was here' watermark."""
    return (
        TelegramMessage.objects.filter(chat_id=chat_id, direction=TelegramMessage.DIRECTION_IN)
        .aggregate(at=Max('created_at'))['at']
    )


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
        'last_tick': _tick_state(latest, _seen_before(chat_id)) if latest else None,
        'unread_count': TelegramMessage.objects.filter(
            chat_id=chat_id, direction=TelegramMessage.DIRECTION_IN, read_at__isnull=True
        ).count(),
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
        watermarks = {cid: _seen_before(cid) for cid in {m.chat_id for m in page}}
        data = [
            _telegram_message_item(m, sellers.get(m.chat_id), watermarks.get(m.chat_id))
            for m in page
        ]
        return paginator.get_paginated_response(data)


class TelegramMessageReplyView(AdminAPIView):
    def post(self, request):
        chat_id = request.data.get('chat_id')
        text = (request.data.get('text') or '').strip()
        if not chat_id or not text:
            return Response({'detail': 'chat_id and text are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = send_telegram_message(chat_id, text)
        except TelegramSendError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        msg = TelegramMessage.objects.create(
            chat_id=chat_id,
            telegram_message_id=result.get('message_id'),
            text=text,
            direction=TelegramMessage.DIRECTION_OUT,
            sent_by=request.user,
        )
        log_audit(request.user, 'telegram_reply', 'telegram_message', msg.pk, request=request)
        seller = _sellers_by_chat_id([chat_id]).get(chat_id)
        return Response(_telegram_message_item(msg, seller), status=status.HTTP_201_CREATED)


class TelegramConversationMarkReadView(AdminAPIView):
    """Marks a chat's incoming messages as read by the admin panel."""

    def post(self, request):
        chat_id = request.data.get('chat_id')
        if not chat_id:
            return Response({'detail': 'chat_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        marked = TelegramMessage.objects.filter(
            chat_id=chat_id, direction=TelegramMessage.DIRECTION_IN, read_at__isnull=True
        ).update(read_at=timezone.now())
        return Response({'detail': 'Marked as read.', 'marked': marked})


class TelegramConversationClearView(AdminAPIView):
    """Deletes a chat everywhere: on Telegram, and every row we keep about it.

    That is the messages, the seller chat link, and this chat's audit trail — a
    cleared conversation must leave nothing behind in the DB, so the clear
    itself is deliberately not logged either.
    """

    def post(self, request):
        chat_id = request.data.get('chat_id')
        if not chat_id:
            return Response({'detail': 'chat_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        chat_messages = TelegramMessage.objects.filter(chat_id=chat_id)
        message_ids = list(
            chat_messages.filter(telegram_message_id__isnull=False).values_list('telegram_message_id', flat=True)
        )
        local_ids = [str(pk) for pk in chat_messages.values_list('pk', flat=True)]
        # Alerts created before telegram_chat_id existed can only be matched by
        # their body, which is the incoming message's text. Materialise the list
        # now — the messages are deleted below, and a lazy queryset would then
        # evaluate to nothing. Blank texts are skipped on purpose: those alerts
        # all share the body "(non-text message)", so matching on it would take
        # other chats' legacy alerts down with this one.
        incoming_texts = list(
            chat_messages.filter(direction=TelegramMessage.DIRECTION_IN)
            .exclude(text='')
            .values_list('text', flat=True)
        )

        deleted, failed = delete_telegram_messages(chat_id, message_ids)
        removed, _ = chat_messages.delete()
        link_removed, _ = TelegramChatLink.objects.filter(chat_id=chat_id).delete()
        alerts_removed, _ = AdminAlert.objects.filter(
            Q(type=AdminAlert.TYPE_TELEGRAM_MESSAGE),
            Q(telegram_chat_id=chat_id) | Q(telegram_chat_id__isnull=True, body__in=incoming_texts),
        ).delete()
        audit_removed, _ = AuditLog.objects.filter(
            Q(target_type='telegram_chat', target_id=str(chat_id))
            | Q(target_type='telegram_message', target_id__in=local_ids)
        ).delete()

        return Response(
            {
                'detail': 'Chat cleared.',
                'telegram_deleted': deleted,
                'telegram_failed': failed,
                'local_removed': removed,
                'link_removed': link_removed,
                'audit_removed': audit_removed,
                'alerts_removed': alerts_removed,
            }
        )
