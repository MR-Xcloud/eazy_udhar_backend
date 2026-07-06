from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from customerapp.models import CustomerAccount
from sellerapp.models import SellerCustomer
from sellerapp.services import refresh_due_status
from sellerapp.utils import seller_customer_phone_exists

from ..services.data import customer_account_detail, customer_account_item, seller_customer_detail, seller_customer_item
from ..utils import log_audit
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


class SellerCustomerDetailView(AdminAPIView):
    def get(self, request, pk):
        try:
            sc = SellerCustomer.objects.select_related('seller', 'linked_customer').get(pk=pk)
        except SellerCustomer.DoesNotExist:
            return Response({'detail': 'Seller customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(seller_customer_detail(sc))

    def patch(self, request, pk):
        try:
            sc = SellerCustomer.objects.select_related('seller', 'linked_customer').get(pk=pk)
        except SellerCustomer.DoesNotExist:
            return Response({'detail': 'Seller customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        update_fields = []
        if 'name' in request.data:
            name = (request.data['name'] or '').strip()
            if not name:
                return Response({'detail': 'Name cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
            sc.name = name
            update_fields.append('name')
        if 'phone' in request.data:
            phone = (request.data['phone'] or '').strip()
            if not phone:
                return Response({'detail': 'Phone cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
            if seller_customer_phone_exists(sc.seller, phone, exclude_id=sc.id):
                return Response(
                    {'detail': 'Another customer with this phone already exists for this seller.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sc.phone = phone
            update_fields.append('phone')
        for field in ('email', 'address', 'city', 'state', 'country'):
            if field in request.data:
                setattr(sc, field, (request.data[field] or '').strip())
                update_fields.append(field)
        if 'outstanding_amount' in request.data:
            try:
                sc.outstanding_amount = Decimal(str(request.data['outstanding_amount']))
            except (InvalidOperation, TypeError):
                return Response(
                    {'detail': 'Invalid outstanding_amount.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            update_fields.append('outstanding_amount')
        if 'next_due_date' in request.data:
            raw = request.data['next_due_date']
            if raw in (None, ''):
                sc.next_due_date = None
            else:
                parsed = parse_date(str(raw))
                if parsed is None:
                    return Response(
                        {'detail': 'next_due_date must be YYYY-MM-DD.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                sc.next_due_date = parsed
            update_fields.append('next_due_date')
        if 'status' in request.data:
            status_value = (request.data['status'] or '').strip().lower()
            status_map = {
                'active': SellerCustomer.STATUS_PENDING,
                'pending': SellerCustomer.STATUS_PENDING,
                'overdue': SellerCustomer.STATUS_OVERDUE,
                'settled': SellerCustomer.STATUS_SETTLED,
                'paid': SellerCustomer.STATUS_PAID,
            }
            if status_value not in status_map:
                return Response({'detail': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)
            sc.status = status_map[status_value]
            update_fields.append('status')

        if update_fields:
            update_fields.append('updated_at')
            sc.save(update_fields=update_fields)
            refresh_due_status(sc)
            _sync_linked_account(sc)
            log_audit(
                request.user,
                'seller_customer_update',
                'seller_customer',
                sc.pk,
                metadata={'fields': update_fields},
                request=request,
            )
        return Response(seller_customer_detail(sc))


def _sync_linked_account(sc):
    if not sc.linked_customer_id:
        return
    from customerapp.messaging import ensure_customer_account

    account = ensure_customer_account(sc, sc.linked_customer)
    account.outstanding_amount = sc.outstanding_amount
    account.next_due_date = sc.next_due_date
    account.advance_deposited = sc.advance_deposited
    account.advance_used = sc.advance_used
    account.has_balance = sc.outstanding_amount > 0
    account.save(
        update_fields=[
            'outstanding_amount',
            'next_due_date',
            'advance_deposited',
            'advance_used',
            'has_balance',
            'updated_at',
        ]
    )


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


class CustomerAccountDetailView(AdminAPIView):
    def get(self, request, pk):
        try:
            account = CustomerAccount.objects.select_related(
                'user', 'seller', 'seller_customer'
            ).get(pk=pk)
        except CustomerAccount.DoesNotExist:
            return Response({'detail': 'Customer account not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(customer_account_detail(account))
