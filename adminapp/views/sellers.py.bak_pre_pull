import secrets
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from sellerapp.models import (
    Seller,
    SellerCustomer,
    SellerDeviceToken,
    SellerNotification,
    SellerSettings,
    TeamMember,
)

from ..models import AccountSuspension, SellerSubscription, SubscriptionPlan
from ..permissions import RoleRequired
from ..services.data import (
    seller_customer_item,
    seller_detail,
    seller_device_item,
    seller_list_item,
    seller_notification_item,
    seller_settings_dict,
    team_member_item,
)
from ..services.moderation import suspend_account, unsuspend_account
from ..services.password_reset import reset_user_password
from ..utils import csv_response, log_audit
from .base import AdminAPIView


def _filter_sellers(request):
    qs = Seller.objects.all().order_by('-created_at')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(business_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
            | Q(full_name__icontains=search)
        )
    status_param = request.query_params.get('status')
    if status_param == 'active':
        qs = qs.filter(is_active=True)
    elif status_param == 'suspended':
        qs = qs.filter(is_active=False)
    sub_status = request.query_params.get('subscription_status')
    if sub_status:
        seller_ids = (
            SellerSubscription.objects.filter(status=sub_status)
            .values_list('seller_id', flat=True)
            .distinct()
        )
        qs = qs.filter(id__in=seller_ids)
    return qs


class SellerListView(AdminAPIView):
    def get(self, request):
        qs = _filter_sellers(request)
        page, paginator = self.paginate(request, qs)
        data = [seller_list_item(s) for s in page]
        return paginator.get_paginated_response(data)


class SellerExportView(AdminAPIView):
    def get(self, request):
        qs = _filter_sellers(request)
        rows = []
        for s in qs[:5000]:
            item = seller_list_item(s)
            rows.append(
                [
                    item['id'],
                    item['business_name'],
                    item['email'],
                    item['phone'],
                    item['customers_count'],
                    item['outstanding_total'],
                    item['status'],
                    item['subscription_status'] or '',
                    item['created_at'],
                ]
            )
        return csv_response(
            'sellers.csv',
            rows,
            [
                'id',
                'business_name',
                'email',
                'phone',
                'customers_count',
                'outstanding_total',
                'status',
                'subscription_status',
                'created_at',
            ],
        )


class SellerInviteView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPPORT, AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if Seller.objects.filter(email=email).exists():
            return Response({'detail': 'A seller with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        business_name = (request.data.get('business_name') or '').strip() or 'My Shop'
        phone = (request.data.get('phone') or '').strip() or '0000000000'
        password = secrets.token_urlsafe(10)

        seller = Seller.objects.create_user(
            username=email,
            email=email,
            password=password,
            business_name=business_name,
            phone=phone,
            full_name=business_name,
        )
        SellerSettings.objects.get_or_create(seller=seller)

        plan = SubscriptionPlan.objects.filter(is_active=True).order_by('sort_order').first()
        if plan and (plan.trial_days or request.data.get('start_trial', True)):
            now = timezone.now()
            trial_days = plan.trial_days or 14
            SellerSubscription.objects.create(
                seller=seller,
                plan=plan,
                status=SellerSubscription.STATUS_TRIAL,
                billing_amount=plan.price_monthly,
                current_period_start=now,
                current_period_end=now + timedelta(days=trial_days),
                trial_ends_at=now + timedelta(days=trial_days),
            )

        log_audit(request.user, 'seller_invite', 'seller', seller.pk, request=request)
        return Response(
            {
                'seller': seller_list_item(seller),
                'message': f'Seller invited. Temporary password: {password}',
            },
            status=status.HTTP_201_CREATED,
        )


class SellerDetailView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(seller_detail(seller))

    def patch(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        allowed = (
            'business_name', 'full_name', 'phone', 'address', 'gst_number', 'email',
            'upi_id', 'bank_account_number', 'bank_ifsc', 'bank_account_holder',
        )
        for field in allowed:
            if field in request.data:
                setattr(seller, field, request.data[field])
        seller.save()
        log_audit(request.user, 'seller_update', 'seller', seller.pk, request=request)
        return Response(seller_detail(seller))


class SellerSummaryView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(seller_detail(seller))


class SellerResetPasswordView(AdminAPIView):
    def post(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)

        send_email = request.data.get('send_email', False)
        password = request.data.get('password')
        ok, payload = reset_user_password(
            user=seller,
            account_type='seller',
            display_name=seller.full_name or seller.business_name,
            send_email=send_email,
            password=password,
        )
        if not ok:
            code = status.HTTP_400_BAD_REQUEST if payload.get('code') == 'invalid_password' else status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(payload, status=code)

        log_audit(request.user, 'reset_password', 'seller', seller.pk, request=request)
        return Response(payload)


class SellerSuspendView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPPORT, AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': 'Reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
        suspend_account(
            request.user,
            account_type=AccountSuspension.ACCOUNT_SELLER,
            account=seller,
            reason=reason,
            request=request,
        )
        return Response({'detail': 'Seller suspended.', 'status': 'suspended'})


class SellerUnsuspendView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPPORT, AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        reason = (request.data.get('reason') or '').strip()
        unsuspend_account(
            request.user,
            account_type=AccountSuspension.ACCOUNT_SELLER,
            account=seller,
            reason=reason,
            request=request,
        )
        return Response({'detail': 'Seller unsuspended.', 'status': 'active'})


class SellerSettingsView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(seller_settings_dict(seller))

    def patch(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        settings, _ = SellerSettings.objects.get_or_create(seller=seller)
        field_map = {
            'reminder_channels': 'reminder_channels',
            'auto_remind_enabled': 'auto_remind_enabled',
            'auto_remind_days_before': 'auto_remind_days_before',
            'auto_remind_time': 'auto_remind_time',
            'daily_summary_enabled': 'daily_summary_enabled',
            'daily_summary_time': 'daily_summary_time',
            'daily_summary_channels': 'daily_summary_channels',
            'push_enabled': 'push_notifications_enabled',
            'push_notifications_enabled': 'push_notifications_enabled',
            'eod_excel_backup_enabled': 'eod_excel_backup_enabled',
            'eod_excel_backup_time': 'eod_excel_backup_time',
            'language': 'language',
        }
        for key, attr in field_map.items():
            if key in request.data:
                setattr(settings, attr, request.data[key])
        settings.save()
        log_audit(request.user, 'seller_settings_update', 'seller', seller.pk, request=request)
        return Response(seller_settings_dict(seller))


class SellerEodBackupSendView(AdminAPIView):
    """Manually trigger a seller's own EOD Excel transaction backup email (for support/testing)."""

    def post(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)

        from sellerapp.eod_excel_report import send_eod_backup_for_seller

        result = send_eod_backup_for_seller(seller, force=True)
        log_audit(request.user, 'seller_eod_backup_send', 'seller', seller.pk, result, request=request)

        if result.get('sent'):
            return Response({'detail': f"Backup emailed to {result['to']}.", **result})
        return Response(
            {'detail': f"Not sent: {result.get('reason') or result.get('error') or 'unknown error'}.", **result},
            status=status.HTTP_400_BAD_REQUEST,
        )


class SellerCustomersView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = SellerCustomer.objects.filter(seller=seller).order_by('-updated_at')
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
        page, paginator = self.paginate(request, qs)
        data = [seller_customer_item(sc) for sc in page]
        return paginator.get_paginated_response(data)


class SellerCustomersExportView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        rows = []
        for sc in SellerCustomer.objects.filter(seller=seller).order_by('name'):
            item = seller_customer_item(sc)
            rows.append(
                [
                    item['id'],
                    item['name'],
                    item['phone'],
                    item['outstanding'],
                    item['status'],
                    item['last_transaction_at'] or '',
                    item['created_at'],
                ]
            )
        return csv_response(
            f'seller-{pk}-customers.csv',
            rows,
            ['id', 'name', 'phone', 'outstanding', 'status', 'last_transaction_at', 'created_at'],
        )


class SellerTeamView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = TeamMember.objects.filter(seller=seller).order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [team_member_item(m) for m in page]
        return paginator.get_paginated_response(data)


class SellerNotificationsView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = SellerNotification.objects.filter(seller=seller).order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [seller_notification_item(n) for n in page]
        return paginator.get_paginated_response(data)


class SellerDevicesView(AdminAPIView):
    def get(self, request, pk):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        qs = SellerDeviceToken.objects.filter(seller=seller).order_by('-updated_at')
        page, paginator = self.paginate(request, qs)
        data = [seller_device_item(dt) for dt in page]
        return paginator.get_paginated_response(data)


class SellerDeviceDeleteView(AdminAPIView):
    def delete(self, request, pk, token_id):
        try:
            seller = Seller.objects.get(pk=pk)
        except Seller.DoesNotExist:
            return Response({'detail': 'Seller not found.'}, status=status.HTTP_404_NOT_FOUND)
        deleted, _ = SellerDeviceToken.objects.filter(seller=seller, pk=token_id).delete()
        if not deleted:
            return Response({'detail': 'Device not found.'}, status=status.HTTP_404_NOT_FOUND)
        log_audit(request.user, 'revoke_device', 'seller', seller.pk, {'token_id': str(token_id)}, request)
        return Response(status=status.HTTP_204_NO_CONTENT)
