from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import SellerJWTAuthentication
from ..models import LedgerTransaction, SellerCustomer
from ..permissions import IsSeller
from ..services import reports_overview, transaction_item
from ..utils import format_inr


class SellerReportView(APIView):
    authentication_classes = [SellerJWTAuthentication]
    permission_classes = [IsSeller]


class ReportsOverviewView(SellerReportView):
    def get(self, request):
        return Response(reports_overview(request.user))


class ReportsCollectionsView(SellerReportView):
    def get(self, request):
        months = int(request.query_params.get('months', 6))
        data = []
        now = timezone.now()
        for i in range(months - 1, -1, -1):
            month = (now.month - i - 1) % 12 + 1
            year = now.year + (now.month - i - 1) // 12
            label = timezone.datetime(year, month, 1).strftime('%b')
            total = (
                LedgerTransaction.objects.filter(
                    seller=request.user,
                    transaction_type=LedgerTransaction.TYPE_PAYMENT,
                    created_at__year=year,
                    created_at__month=month,
                ).aggregate(t=Sum('amount'))['t']
                or 0
            )
            data.append({'label': label, 'value': float(total)})
        return Response({'collections': data})


class ReportsDueView(SellerReportView):
    def get(self, request):
        customers = SellerCustomer.objects.filter(
            seller=request.user, outstanding_amount__gt=0
        )
        rows = [
            {
                'customer_id': str(c.id),
                'name': c.name,
                'phone': c.phone,
                'outstanding': float(c.outstanding_amount),
                'outstanding_display': format_inr(c.outstanding_amount),
                'status': c.status,
            }
            for c in customers
        ]
        return Response(
            {
                'report': 'due',
                'generated_at': timezone.now().isoformat(),
                'rows': rows,
            }
        )


class ReportsCollectionView(SellerReportView):
    def get(self, request):
        txs = LedgerTransaction.objects.filter(
            seller=request.user,
            transaction_type=LedgerTransaction.TYPE_PAYMENT,
        )[:100]
        return Response(
            {
                'report': 'collection',
                'transactions': [transaction_item(tx) for tx in txs],
            }
        )


class ReportsMonthlySummaryView(SellerReportView):
    def get(self, request):
        credit = (
            LedgerTransaction.objects.filter(
                seller=request.user,
                transaction_type=LedgerTransaction.TYPE_CREDIT,
            ).aggregate(t=Sum('amount'))['t']
            or 0
        )
        received = (
            LedgerTransaction.objects.filter(
                seller=request.user,
                transaction_type=LedgerTransaction.TYPE_PAYMENT,
            ).aggregate(t=Sum('amount'))['t']
            or 0
        )
        return Response(
            {
                'report': 'monthly_summary',
                'total_credit_given': float(credit),
                'total_collected': float(received),
                'gst_note': 'Configure GST in business profile for tax reports.',
            }
        )


class CustomerStatementReportView(SellerReportView):
    def get(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        txs = LedgerTransaction.objects.filter(customer=customer)
        return Response(
            {
                'report': 'customer_statement',
                'customer': customer.name,
                'outstanding': float(customer.outstanding_amount),
                'transactions': [transaction_item(tx) for tx in txs],
            }
        )
