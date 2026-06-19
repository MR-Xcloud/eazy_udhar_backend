from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.response import Response

from customerapp.models import CustomerPayment, PaymentMethod, RazorpayPaymentOrder
from customerapp.razorpay_service import razorpay_configured
from easyudhar.payment_utils import payment_method_label, payment_methods_catalog
from easyudhar.razorpay_config import get_razorpay_credentials
from sellerapp.models import SellerPaymentLink, SellerRazorpayOrder

from ..services.data import (
    customer_razorpay_order_item,
    customer_saved_payment_method_item,
    seller_payment_link_item,
    seller_razorpay_order_item,
)
from .base import AdminAPIView


class PaymentOverviewView(AdminAPIView):
    def get(self, request):
        today = timezone.localdate()
        customer_payments = CustomerPayment.objects.filter(status=CustomerPayment.STATUS_SUCCESS)
        ledger_orders_pending = (
            RazorpayPaymentOrder.objects.filter(status=RazorpayPaymentOrder.STATUS_PENDING).count()
            + SellerRazorpayOrder.objects.filter(status=SellerRazorpayOrder.STATUS_PENDING).count()
        )
        key_id, _, _ = get_razorpay_credentials()
        return Response(
            {
                'customer_payments_total': customer_payments.count(),
                'customer_payments_today': customer_payments.filter(
                    created_at__date=today
                ).count(),
                'customer_payments_amount_today': float(
                    customer_payments.filter(created_at__date=today).aggregate(
                        t=Sum('amount')
                    )['t']
                    or 0
                ),
                'pending_checkout_orders': ledger_orders_pending,
                'paid_checkout_orders_today': (
                    RazorpayPaymentOrder.objects.filter(
                        status=RazorpayPaymentOrder.STATUS_PAID, paid_at__date=today
                    ).count()
                    + SellerRazorpayOrder.objects.filter(
                        status=SellerRazorpayOrder.STATUS_PAID, paid_at__date=today
                    ).count()
                ),
                'active_payment_links': SellerPaymentLink.objects.filter(
                    status__in=(
                        SellerPaymentLink.STATUS_ACTIVE,
                        SellerPaymentLink.STATUS_PARTIAL,
                    )
                ).count(),
                'failed_checkout_orders': (
                    RazorpayPaymentOrder.objects.filter(
                        status=RazorpayPaymentOrder.STATUS_FAILED
                    ).count()
                    + SellerRazorpayOrder.objects.filter(
                        status=SellerRazorpayOrder.STATUS_FAILED
                    ).count()
                ),
                'razorpay_configured': razorpay_configured(),
                'razorpay_mode': settings.RAZORPAY_MODE,
                'razorpay_key_id': key_id or None,
            }
        )


class AdminRazorpayConfigView(AdminAPIView):
    def get(self, request):
        from django.conf import settings

        key_id, _, _ = get_razorpay_credentials()
        return Response(
            {
                'configured': razorpay_configured(),
                'key_id': key_id or None,
                'mode': settings.RAZORPAY_MODE,
                'partial_payment_allowed': True,
                'online_gateway': 'razorpay',
            }
        )


class AdminPaymentMethodsView(AdminAPIView):
    def get(self, request):
        online = request.query_params.get('online', '').lower() in ('1', 'true', 'yes')
        return Response(
            {
                'methods': payment_methods_catalog(online=online),
                'seller_manual': payment_methods_catalog(online=False),
                'customer_online': payment_methods_catalog(online=True),
            }
        )


class CheckoutOrdersListView(AdminAPIView):
    def get(self, request):
        source = (request.query_params.get('source') or 'all').lower()
        status = request.query_params.get('status')
        seller_id = request.query_params.get('seller_id')
        customer_id = request.query_params.get('customer_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        search = (request.query_params.get('search') or '').strip()

        rows = []

        if source in ('all', 'customer'):
            qs = RazorpayPaymentOrder.objects.select_related('user').order_by('-created_at')
            if status:
                qs = qs.filter(status=status)
            if customer_id:
                qs = qs.filter(user_id=customer_id)
            if date_from:
                qs = qs.filter(created_at__date__gte=date_from)
            if date_to:
                qs = qs.filter(created_at__date__lte=date_to)
            if search:
                qs = qs.filter(
                    Q(reference_id__icontains=search)
                    | Q(razorpay_order_id__icontains=search)
                    | Q(razorpay_payment_id__icontains=search)
                    | Q(user__email__icontains=search)
                )
            rows.extend(customer_razorpay_order_item(o) for o in qs[:500])

        if source in ('all', 'seller'):
            qs = SellerRazorpayOrder.objects.select_related(
                'seller', 'customer'
            ).order_by('-created_at')
            if status:
                qs = qs.filter(status=status)
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
                    Q(reference_id__icontains=search)
                    | Q(razorpay_order_id__icontains=search)
                    | Q(customer__name__icontains=search)
                    | Q(seller__business_name__icontains=search)
                )
            rows.extend(seller_razorpay_order_item(o) for o in qs[:500])

        rows.sort(key=lambda r: r['created_at'], reverse=True)
        page_num = max(int(request.query_params.get('page', 1) or 1), 1)
        page_size = min(max(int(request.query_params.get('page_size', 25) or 25), 1), 100)
        start = (page_num - 1) * page_size
        page_rows = rows[start : start + page_size]
        return Response(
            {
                'count': len(rows),
                'next': page_num + 1 if start + page_size < len(rows) else None,
                'previous': page_num - 1 if page_num > 1 else None,
                'results': page_rows,
            }
        )


class PaymentLinksListView(AdminAPIView):
    def get(self, request):
        qs = SellerPaymentLink.objects.select_related('seller', 'customer').annotate(
            payments_count=Count('payments')
        ).order_by('-created_at')
        status = request.query_params.get('status')
        seller_id = request.query_params.get('seller_id')
        if status:
            qs = qs.filter(status=status)
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(reference_id__icontains=search)
                | Q(customer__name__icontains=search)
                | Q(seller__business_name__icontains=search)
            )
        page, paginator = self.paginate(request, qs)
        data = [seller_payment_link_item(link) for link in page]
        return paginator.get_paginated_response(data)


class SavedPaymentMethodsListView(AdminAPIView):
    def get(self, request):
        qs = PaymentMethod.objects.select_related('user').order_by('-created_at')
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            qs = qs.filter(user_id=customer_id)
        page, paginator = self.paginate(request, qs)
        data = [customer_saved_payment_method_item(m) for m in page]
        return paginator.get_paginated_response(data)
