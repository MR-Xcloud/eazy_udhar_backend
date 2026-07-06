from django.db.models import Q

from sellerapp.models import SellerSmsPackOrder

from ..services.sms_packs import sms_pack_order_to_dict
from .base import AdminAPIView


class SmsPackOrderListView(AdminAPIView):
    def get(self, request):
        qs = SellerSmsPackOrder.objects.select_related('seller').order_by('-created_at')

        status_param = (request.query_params.get('status') or '').strip()
        if status_param:
            qs = qs.filter(status=status_param)

        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)

        pack_slug = (request.query_params.get('pack_slug') or '').strip()
        if pack_slug:
            qs = qs.filter(pack_slug=pack_slug)

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(reference_id__icontains=search)
                | Q(razorpay_order_id__icontains=search)
                | Q(razorpay_payment_id__icontains=search)
                | Q(pack_name__icontains=search)
                | Q(pack_slug__icontains=search)
                | Q(seller__business_name__icontains=search)
                | Q(seller__email__icontains=search)
            )

        page, paginator = self.paginate(request, qs)
        data = [sms_pack_order_to_dict(order) for order in page]
        return paginator.get_paginated_response(data)
