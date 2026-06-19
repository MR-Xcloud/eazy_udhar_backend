from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from customerapp.models import ShopMessage

from ..models import AccountSuspension, SupportTicket, TicketReply
from ..services.data import shop_message_item
from ..utils import log_audit
from .base import AdminAPIView


def _suspension_item(suspension):
    account_id = suspension.seller_id if suspension.account_type == AccountSuspension.ACCOUNT_SELLER else suspension.customer_id
    return {
        'id': suspension.id,
        'account_type': suspension.account_type,
        'account_id': account_id,
        'account_name': suspension.account_name,
        'reason': suspension.reason,
        'suspended_by_admin_id': suspension.suspended_by_id,
        'suspended_by_admin_email': suspension.suspended_by.email if suspension.suspended_by_id else '',
        'suspended_at': suspension.suspended_at.isoformat(),
        'lifted_at': suspension.lifted_at.isoformat() if suspension.lifted_at else None,
        'is_active': suspension.is_active,
    }


def _ticket_item(ticket):
    requester_id = ticket.seller_id if ticket.requester_type == SupportTicket.REQUESTER_SELLER else ticket.customer_id
    return {
        'id': ticket.id,
        'subject': ticket.subject,
        'description': ticket.description,
        'status': ticket.status,
        'priority': ticket.priority,
        'requester_type': ticket.requester_type,
        'requester_id': requester_id,
        'assigned_to_admin_id': ticket.assigned_to_id,
        'created_at': ticket.created_at.isoformat(),
        'updated_at': ticket.updated_at.isoformat(),
    }


class SuspensionListView(AdminAPIView):
    def get(self, request):
        qs = AccountSuspension.objects.select_related('suspended_by').order_by('-suspended_at')
        status_param = request.query_params.get('status')
        if status_param == 'active':
            qs = qs.filter(is_active=True)
        elif status_param == 'historical':
            qs = qs.filter(is_active=False)
        account_type = request.query_params.get('account_type')
        if account_type:
            qs = qs.filter(account_type=account_type)
        page, paginator = self.paginate(request, qs)
        data = [_suspension_item(s) for s in page]
        return paginator.get_paginated_response(data)


class MessageListView(AdminAPIView):
    def get(self, request):
        qs = ShopMessage.objects.select_related('seller', 'seller_customer', 'customer_user').order_by('-created_at')
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            qs = qs.filter(
                Q(customer_user_id=customer_id)
                | Q(seller_customer__linked_customer_id=customer_id)
            )
        flagged = request.query_params.get('flagged')
        if flagged == 'true':
            # Migration note: add `flagged` BooleanField to ShopMessage if filtering is needed.
            if hasattr(ShopMessage, 'flagged'):
                qs = qs.filter(flagged=True)
        page, paginator = self.paginate(request, qs)
        data = [shop_message_item(m) for m in page]
        return paginator.get_paginated_response(data)


class MessageFlagView(AdminAPIView):
    def post(self, request, pk):
        try:
            msg = ShopMessage.objects.get(pk=pk)
        except ShopMessage.DoesNotExist:
            return Response({'detail': 'Message not found.'}, status=status.HTTP_404_NOT_FOUND)
        # Migration note: add `flagged` BooleanField to ShopMessage model.
        if hasattr(msg, 'flagged'):
            msg.flagged = True
            msg.save(update_fields=['flagged'])
        log_audit(request.user, 'flag_message', 'shop_message', msg.pk, request=request)
        return Response(shop_message_item(msg))


class MessageDeleteView(AdminAPIView):
    def delete(self, request, pk):
        try:
            msg = ShopMessage.objects.get(pk=pk)
        except ShopMessage.DoesNotExist:
            return Response({'detail': 'Message not found.'}, status=status.HTTP_404_NOT_FOUND)
        msg_id = msg.pk
        msg.delete()
        log_audit(request.user, 'delete_message', 'shop_message', msg_id, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TicketListView(AdminAPIView):
    def get(self, request):
        qs = SupportTicket.objects.select_related('assigned_to', 'seller', 'customer').order_by('-updated_at')
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        priority = request.query_params.get('priority')
        if priority:
            qs = qs.filter(priority=priority)
        assigned_to = request.query_params.get('assigned_to')
        if assigned_to:
            qs = qs.filter(assigned_to_id=assigned_to)
        page, paginator = self.paginate(request, qs)
        data = [_ticket_item(t) for t in page]
        return paginator.get_paginated_response(data)


class TicketDetailView(AdminAPIView):
    def patch(self, request, pk):
        try:
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return Response({'detail': 'Ticket not found.'}, status=status.HTTP_404_NOT_FOUND)
        if 'status' in request.data:
            ticket.status = request.data['status']
        if 'priority' in request.data:
            ticket.priority = request.data['priority']
        assigned = request.data.get('assigned_to_admin_id')
        if assigned is not None:
            ticket.assigned_to_id = assigned or None
        ticket.save()
        log_audit(request.user, 'ticket_update', 'ticket', ticket.pk, request=request)
        return Response(_ticket_item(ticket))


class TicketReplyView(AdminAPIView):
    def post(self, request, pk):
        try:
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return Response({'detail': 'Ticket not found.'}, status=status.HTTP_404_NOT_FOUND)
        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'detail': 'Reply body is required.'}, status=status.HTTP_400_BAD_REQUEST)
        reply = TicketReply.objects.create(ticket=ticket, admin=request.user, body=body)
        log_audit(request.user, 'ticket_reply', 'ticket', ticket.pk, request=request)
        return Response(
            {
                'id': reply.id,
                'ticket_id': ticket.id,
                'body': reply.body,
                'created_at': reply.created_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )
