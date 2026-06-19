from django.db.models import Q

from customerapp.models import CustomerAccount
from sellerapp.models import SellerCustomer

from ..services.data import customer_account_item, seller_customer_item
from .base import AdminAPIView


class SellerCustomersGlobalListView(AdminAPIView):
    def get(self, request):
        qs = SellerCustomer.objects.select_related('seller').order_by('-updated_at')
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        status_param = request.query_params.get('status')
        if status_param == 'overdue':
            qs = qs.filter(status=SellerCustomer.STATUS_OVERDUE)
        elif status_param == 'settled':
            qs = qs.filter(status__in=[SellerCustomer.STATUS_SETTLED, SellerCustomer.STATUS_PAID])
        elif status_param == 'active':
            qs = qs.filter(status=SellerCustomer.STATUS_PENDING)
        page, paginator = self.paginate(request, qs)
        data = [seller_customer_item(sc) for sc in page]
        return paginator.get_paginated_response(data)


class CustomerAccountsGlobalListView(AdminAPIView):
    def get(self, request):
        qs = CustomerAccount.objects.select_related('user', 'seller').order_by('-created_at')
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(shop_name__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(user__email__icontains=search)
            )
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            qs = qs.filter(user_id=customer_id)
        page, paginator = self.paginate(request, qs)
        data = [customer_account_item(a) for a in page]
        return paginator.get_paginated_response(data)
