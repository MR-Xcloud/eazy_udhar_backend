from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from customerapp.models import CustomerPayment
from sellerapp.models import LedgerTransaction

from ..models import RazorpayPayment, SyncQueueItem
from ..services.data import customer_payment_item, ledger_transaction_item
from ..utils import log_audit
from .base import AdminAPIView


def _sync_queue_item(item):
    return {
        'id': item.id,
        'seller_id': item.seller_id,
        'seller_name': item.seller.business_name,
        'operation_type': item.operation_type,
        'payload_summary': item.payload_summary,
        'status': item.status,
        'error_message': item.error_message,
        'created_at': item.created_at.isoformat(),
        'retry_count': item.retry_count,
    }


def _razorpay_transaction_item(payment):
    return {
        'id': payment.id,
        'seller_id': payment.seller_id,
        'seller_customer_id': None,
        'customer_name': payment.seller.business_name,
        'type': 'razorpay_payment',
        'amount': float(payment.amount),
        'balance_after': None,
        'note': payment.order_id,
        'created_by': 'razorpay',
        'created_at': payment.created_at.isoformat(),
        'source': 'razorpay',
    }


class TransactionListView(AdminAPIView):
    def get(self, request):
        tx_type = (request.query_params.get('type') or 'ledger').lower()
        seller_id = request.query_params.get('seller_id')
        customer_id = request.query_params.get('customer_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        search = (request.query_params.get('search') or '').strip()

        if tx_type == 'payment':
            qs = CustomerPayment.objects.select_related('account', 'user').order_by('-created_at')
            if seller_id:
                qs = qs.filter(account__seller_id=seller_id)
            if customer_id:
                qs = qs.filter(user_id=customer_id)
            if date_from:
                qs = qs.filter(created_at__date__gte=date_from)
            if date_to:
                qs = qs.filter(created_at__date__lte=date_to)
            page, paginator = self.paginate(request, qs)
            data = [customer_payment_item(p) for p in page]
            return paginator.get_paginated_response(data)

        if tx_type == 'razorpay':
            qs = RazorpayPayment.objects.select_related('seller').order_by('-created_at')
            if seller_id:
                qs = qs.filter(seller_id=seller_id)
            if date_from:
                qs = qs.filter(created_at__date__gte=date_from)
            if date_to:
                qs = qs.filter(created_at__date__lte=date_to)
            if search:
                qs = qs.filter(
                    Q(order_id__icontains=search) | Q(payment_id__icontains=search)
                )
            page, paginator = self.paginate(request, qs)
            data = [_razorpay_transaction_item(p) for p in page]
            return paginator.get_paginated_response(data)

        qs = LedgerTransaction.objects.select_related('seller', 'customer').order_by('-created_at')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        if customer_id:
            qs = qs.filter(customer__linked_customer_id=customer_id)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if search:
            qs = qs.filter(
                Q(customer__name__icontains=search)
                | Q(note__icontains=search)
                | Q(seller__business_name__icontains=search)
            )
        page, paginator = self.paginate(request, qs)
        data = [ledger_transaction_item(tx) for tx in page]
        return paginator.get_paginated_response(data)


class SyncQueueListView(AdminAPIView):
    def get(self, request):
        qs = SyncQueueItem.objects.select_related('seller').order_by('-created_at')
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        page, paginator = self.paginate(request, qs)
        data = [_sync_queue_item(item) for item in page]
        return paginator.get_paginated_response(data)


class SyncQueueRetryView(AdminAPIView):
    def post(self, request, pk):
        try:
            item = SyncQueueItem.objects.get(pk=pk)
        except SyncQueueItem.DoesNotExist:
            return Response({'detail': 'Sync item not found.'}, status=status.HTTP_404_NOT_FOUND)
        item.status = SyncQueueItem.STATUS_PENDING
        item.retry_count += 1
        item.error_message = ''
        item.save(update_fields=['status', 'retry_count', 'error_message'])
        log_audit(request.user, 'sync_retry', 'sync_queue', item.pk, request=request)
        return Response(_sync_queue_item(item))


class SyncQueueDismissView(AdminAPIView):
    def post(self, request, pk):
        try:
            item = SyncQueueItem.objects.get(pk=pk)
        except SyncQueueItem.DoesNotExist:
            return Response({'detail': 'Sync item not found.'}, status=status.HTTP_404_NOT_FOUND)
        item.status = SyncQueueItem.STATUS_DUPLICATE
        item.save(update_fields=['status'])
        log_audit(request.user, 'sync_dismiss', 'sync_queue', item.pk, request=request)
        return Response(_sync_queue_item(item))
