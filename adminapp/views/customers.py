import secrets

from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from customerapp.models import (
    Customer,
    CustomerAccount,
    CustomerDeviceToken,
    CustomerNotification,
    CustomerPayment,
    ShopMessage,
)

from ..models import AccountSuspension
from ..permissions import RoleRequired
from ..services.data import (
    customer_account_item,
    customer_detail,
    customer_device_item,
    customer_list_item,
    customer_notification_item,
    customer_payment_item,
    shop_message_item,
)
from ..services.moderation import suspend_account, unsuspend_account
from ..utils import csv_response, log_audit
from .base import AdminAPIView


def _filter_customers(request):
    qs = Customer.objects.all().order_by('-created_at')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
            | Q(username__icontains=search)
        )
    status_param = request.query_params.get('status')
    if status_param == 'active':
        qs = qs.filter(is_active=True)
    elif status_param == 'suspended':
        qs = qs.filter(is_active=False)
    return qs


class CustomerListView(AdminAPIView):
    def get(self, request):
        qs = _filter_customers(request).exclude(is_superuser=True)
        page, paginator = self.paginate(request, qs)
        data = [customer_list_item(c) for c in page]
        return paginator.get_paginated_response(data)


class CustomerExportView(AdminAPIView):
    def get(self, request):
        qs = _filter_customers(request).exclude(is_superuser=True)
        rows = []
        for c in qs[:5000]:
            item = customer_list_item(c)
            rows.append(
                [
                    item['id'],
                    item['full_name'],
                    item['email'],
                    item['phone'],
                    item['promo_code'] or '',
                    item['linked_shops'],
                    item['status'],
                    item['created_at'],
                ]
            )
        return csv_response(
            'customers.csv',
            rows,
            ['id', 'full_name', 'email', 'phone', 'promo_code', 'linked_shops', 'status', 'created_at'],
        )


class CustomerDetailView(AdminAPIView):
    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(customer_detail(customer))

    def patch(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        if 'promo_code' in request.data:
            customer.promo_code = request.data['promo_code'] or ''
            customer.save(update_fields=['promo_code'])
            log_audit(request.user, 'customer_promo_update', 'customer', customer.pk, request=request)
        return Response(customer_detail(customer))


class CustomerResetPasswordView(AdminAPIView):
    def post(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        temp_password = secrets.token_urlsafe(10)
        customer.set_password(temp_password)
        customer.save(update_fields=['password'])
        log_audit(request.user, 'reset_password', 'customer', customer.pk, request=request)
        return Response({'message': f'Password reset. Temporary password: {temp_password}'})


class CustomerSuspendView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPPORT, AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': 'Reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
        suspend_account(
            request.user,
            account_type=AccountSuspension.ACCOUNT_CUSTOMER,
            account=customer,
            reason=reason,
            request=request,
        )
        return Response({'detail': 'Customer suspended.', 'status': 'suspended'})


class CustomerUnsuspendView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPPORT, AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        reason = (request.data.get('reason') or '').strip()
        unsuspend_account(
            request.user,
            account_type=AccountSuspension.ACCOUNT_CUSTOMER,
            account=customer,
            reason=reason,
            request=request,
        )
        return Response({'detail': 'Customer unsuspended.', 'status': 'active'})


class CustomerAccountsView(AdminAPIView):
    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = CustomerAccount.objects.filter(user=customer).select_related('seller', 'user').order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [customer_account_item(a) for a in page]
        return paginator.get_paginated_response(data)


class CustomerAccountDeleteView(AdminAPIView):
    def delete(self, request, pk, account_id):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        deleted, _ = CustomerAccount.objects.filter(user=customer, pk=account_id).delete()
        if not deleted:
            return Response({'detail': 'Account not found.'}, status=status.HTTP_404_NOT_FOUND)
        log_audit(request.user, 'unlink_account', 'customer', customer.pk, {'account_id': str(account_id)}, request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomerPaymentsView(AdminAPIView):
    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = CustomerPayment.objects.filter(user=customer).select_related('account').order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [customer_payment_item(p) for p in page]
        return paginator.get_paginated_response(data)


class CustomerNotificationsView(AdminAPIView):
    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = CustomerNotification.objects.filter(user=customer).order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [customer_notification_item(n) for n in page]
        return paginator.get_paginated_response(data)


class CustomerMessagesView(AdminAPIView):
    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = ShopMessage.objects.filter(customer_user=customer).order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [shop_message_item(m) for m in page]
        return paginator.get_paginated_response(data)


class CustomerDevicesView(AdminAPIView):
    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = CustomerDeviceToken.objects.filter(user=customer).order_by('-updated_at')
        page, paginator = self.paginate(request, qs)
        data = [customer_device_item(dt) for dt in page]
        return paginator.get_paginated_response(data)


class CustomerDeviceDeleteView(AdminAPIView):
    def delete(self, request, pk, token_id):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        deleted, _ = CustomerDeviceToken.objects.filter(user=customer, pk=token_id).delete()
        if not deleted:
            return Response({'detail': 'Device not found.'}, status=status.HTTP_404_NOT_FOUND)
        log_audit(request.user, 'revoke_device', 'customer', customer.pk, {'token_id': str(token_id)}, request)
        return Response(status=status.HTTP_204_NO_CONTENT)
