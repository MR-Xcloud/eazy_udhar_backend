
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
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

from ..models import AccountSuspension, AdminUser, CustomerBackup
from ..permissions import RoleRequired
from ..services.backups import build_customer_backup_payload, restore_customer_backup
from ..services.data import (
    customer_account_item,
    customer_backup_item,
    customer_detail,
    customer_device_item,
    customer_list_item,
    customer_notification_item,
    customer_payment_item,
    shop_message_item,
)
from ..services.moderation import suspend_account, unsuspend_account
from ..services.password_reset import reset_user_password
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
            | Q(signup_city__icontains=search)
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
                    item['signup_location'] or '',
                    item['signup_ip'] or '',
                ]
            )
        return csv_response(
            'customers.csv',
            rows,
            [
                'id', 'full_name', 'email', 'phone', 'promo_code', 'linked_shops',
                'status', 'created_at', 'signup_location', 'signup_ip',
            ],
        )


def _customer_has_financial_history(customer):
    return (
        customer.accounts.exists()
        or customer.payments.exists()
        or customer.razorpay_orders.exists()
    )


class CustomerDetailView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method == 'DELETE':
            perms.append(RoleRequired([AdminUser.ROLE_SUPER_ADMIN]))
        return perms

    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(customer_detail(customer))

    def delete(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        if _customer_has_financial_history(customer):
            return Response(
                {
                    'detail': (
                        'This customer has linked shop accounts, payments, or orders. '
                        'Suspend the account instead of deleting it.'
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
        name = customer.full_name or customer.username
        log_audit(request.user, 'customer_delete', 'customer', customer.pk, {'name': name}, request=request)
        customer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        update_fields = []
        if 'promo_code' in request.data:
            customer.promo_code = request.data['promo_code'] or ''
            update_fields.append('promo_code')
        if 'full_name' in request.data:
            customer.full_name = (request.data['full_name'] or '').strip() or None
            update_fields.append('full_name')
        if 'phone' in request.data:
            phone = (request.data['phone'] or '').strip()
            if not phone:
                return Response(
                    {'detail': 'Phone cannot be empty.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            customer.phone = phone
            update_fields.append('phone')
        if 'email' in request.data:
            email = (request.data['email'] or '').strip().lower()
            if not email:
                return Response(
                    {'detail': 'Email cannot be empty.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if Customer.objects.exclude(pk=pk).filter(email__iexact=email).exists():
                return Response(
                    {'detail': 'Email already in use.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            customer.email = email
            update_fields.append('email')
            # Keep username mirroring email (registration always sets them equal) —
            # a stale username here is what silently broke login for customer #4.
            if customer.username != email:
                customer.username = email
                update_fields.append('username')

        if update_fields:
            update_fields.append('updated_at')
            customer.save(update_fields=update_fields)
            log_audit(
                request.user,
                'customer_update',
                'customer',
                customer.pk,
                metadata={'fields': update_fields},
                request=request,
            )
        return Response(customer_detail(customer))


class CustomerBulkDeleteView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request):
        ids = request.data.get('ids')
        if not isinstance(ids, list) or not ids:
            return Response({'detail': 'No customer ids provided.'}, status=status.HTTP_400_BAD_REQUEST)

        deleted = []
        blocked = []
        for customer in Customer.objects.filter(pk__in=ids):
            name = customer.full_name or customer.username
            if _customer_has_financial_history(customer):
                blocked.append({'id': customer.id, 'name': name})
                continue
            log_audit(request.user, 'customer_delete', 'customer', customer.pk, {'name': name}, request=request)
            customer.delete()
            deleted.append(customer.id)

        return Response({'deleted': deleted, 'blocked': blocked})


class CustomerResetPasswordView(AdminAPIView):
    def post(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        send_email = request.data.get('send_email', False)
        password = request.data.get('password')
        ok, payload = reset_user_password(
            user=customer,
            account_type='customer',
            display_name=customer.full_name or customer.username,
            send_email=send_email,
            password=password,
        )
        if not ok:
            code = status.HTTP_400_BAD_REQUEST if payload.get('code') == 'invalid_password' else status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(payload, status=code)

        log_audit(request.user, 'reset_password', 'customer', customer.pk, request=request)
        return Response(payload)


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


class CustomerBackupListView(AdminAPIView):
    def get_permissions(self):
        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method == 'POST':
            perms.append(RoleRequired([AdminUser.ROLE_SUPPORT, AdminUser.ROLE_SUPER_ADMIN]))
        return perms

    def get(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = CustomerBackup.objects.filter(customer=customer).select_related('created_by', 'restored_by')
        page, paginator = self.paginate(request, qs)
        data = [customer_backup_item(b) for b in page]
        return paginator.get_paginated_response(data)

    def post(self, request, pk):
        try:
            customer = Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        label = (request.data.get('label') or '').strip()
        payload = build_customer_backup_payload(customer)
        backup = CustomerBackup.objects.create(
            customer=customer,
            label=label,
            payload=payload,
            created_by=request.user,
        )
        log_audit(
            request.user, 'customer_backup_create', 'customer', customer.pk,
            {'backup_id': backup.id}, request=request,
        )
        return Response(customer_backup_item(backup), status=status.HTTP_201_CREATED)


def _get_customer_backup(pk, backup_id):
    customer = Customer.objects.filter(pk=pk).first()
    if customer is None:
        return None, None
    backup = CustomerBackup.objects.filter(pk=backup_id, customer=customer).first()
    return customer, backup


class CustomerBackupDetailView(AdminAPIView):
    def get_permissions(self):
        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method == 'DELETE':
            perms.append(RoleRequired([AdminUser.ROLE_SUPER_ADMIN]))
        return perms

    def get(self, request, pk, backup_id):
        customer, backup = _get_customer_backup(pk, backup_id)
        if customer is None:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        if backup is None:
            return Response({'detail': 'Backup not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(customer_backup_item(backup))

    def delete(self, request, pk, backup_id):
        customer, backup = _get_customer_backup(pk, backup_id)
        if customer is None:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        if backup is None:
            return Response({'detail': 'Backup not found.'}, status=status.HTTP_404_NOT_FOUND)
        log_audit(
            request.user, 'customer_backup_delete', 'customer', customer.pk,
            {'backup_id': backup.id}, request=request,
        )
        backup.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomerBackupDownloadView(AdminAPIView):
    def get(self, request, pk, backup_id):
        customer, backup = _get_customer_backup(pk, backup_id)
        if customer is None:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        if backup is None:
            return Response({'detail': 'Backup not found.'}, status=status.HTTP_404_NOT_FOUND)
        response = JsonResponse(backup.payload, json_dumps_params={'indent': 2})
        response['Content-Disposition'] = f'attachment; filename="customer-{customer.pk}-backup-{backup.id}.json"'
        return response


class CustomerBackupRestoreView(AdminAPIView):
    def get_permissions(self):
        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, pk, backup_id):
        customer, backup = _get_customer_backup(pk, backup_id)
        if customer is None:
            return Response({'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        if backup is None:
            return Response({'detail': 'Backup not found.'}, status=status.HTTP_404_NOT_FOUND)

        restore_customer_backup(customer, backup)
        backup.restored_at = timezone.now()
        backup.restored_by = request.user
        backup.save(update_fields=['restored_at', 'restored_by'])

        log_audit(
            request.user, 'customer_backup_restore', 'customer', customer.pk,
            {'backup_id': backup.id}, request=request,
        )
        return Response(customer_detail(customer))
