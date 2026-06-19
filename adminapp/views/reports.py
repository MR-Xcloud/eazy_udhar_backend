from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.response import Response

from sellerapp.models import LedgerTransaction, SellerCustomer, SellerNotification
from sellerapp.services import _transaction_effective_date

from ..services.dashboard import collections_chart
from ..utils import csv_response
from .base import AdminAPIView


class ReportsCollectionsView(AdminAPIView):
    def get(self, request):
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        seller_id = request.query_params.get('seller_id')
        group_by = request.query_params.get('group_by', 'day')

        if date_from and date_to:
            range_param = '90d'
        else:
            range_param = request.query_params.get('range', '30d')

        chart = collections_chart(range_param)
        data = chart['data']

        if seller_id:
            buckets = {}
            qs = LedgerTransaction.objects.filter(
                seller_id=seller_id,
                transaction_type=LedgerTransaction.TYPE_PAYMENT,
            )
            for tx in qs.only('amount', 'created_at', 'device_created_at'):
                key = _transaction_effective_date(tx).date().isoformat()
                if key not in buckets:
                    buckets[key] = {'date': key, 'collections': 0.0, 'credits': 0.0}
                buckets[key]['collections'] += float(tx.amount)
            data = list(buckets.values())

        return Response({'group_by': group_by, 'data': data})


class ReportsOverdueView(AdminAPIView):
    def get(self, request):
        min_amount = request.query_params.get('min_amount')
        qs = (
            SellerCustomer.objects.filter(status=SellerCustomer.STATUS_OVERDUE)
            .values('seller_id', 'seller__business_name')
            .annotate(
                overdue_count=Count('id'),
                overdue_amount=Sum('outstanding_amount'),
            )
            .order_by('-overdue_amount')
        )
        if min_amount:
            try:
                qs = qs.filter(outstanding_amount__gte=Decimal(min_amount))
            except Exception:
                pass

        page, paginator = self.paginate(request, qs)
        data = [
            {
                'seller_id': row['seller_id'],
                'seller_name': row['seller__business_name'],
                'overdue_count': row['overdue_count'],
                'overdue_amount': float(row['overdue_amount'] or 0),
            }
            for row in page
        ]
        return paginator.get_paginated_response(data)


class ReportsDailySummaryView(AdminAPIView):
    def get(self, request):
        qs = SellerNotification.objects.filter(
            notification_type=SellerNotification.TYPE_DAILY_SUMMARY
        ).select_related('seller').order_by('-created_at')
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        page, paginator = self.paginate(request, qs)
        data = [
            {
                'id': str(n.id),
                'seller_id': n.seller_id,
                'seller_name': n.seller.business_name,
                'title': n.title,
                'body': n.subtitle,
                'status': 'sent',
                'created_at': n.created_at.isoformat(),
            }
            for n in page
        ]
        return paginator.get_paginated_response(data)


class ReportsExportView(AdminAPIView):
    def get(self, request):
        range_param = request.query_params.get('range', '30d')
        chart = collections_chart(range_param)
        rows = [
            [row['date'], row['collections'], row['credits']]
            for row in chart['data']
        ]
        return csv_response('report-export.csv', rows, ['date', 'collections', 'credits'])
