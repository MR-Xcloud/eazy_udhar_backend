from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import SellerJWTAuthentication
from customerapp.messaging import (
    get_thread_messages,
    link_seller_customer,
    message_to_dict,
    send_seller_message,
)
from ..device_tokens import register_seller_device_token, unregister_seller_device_token
from ..models import (
    CallLog,
    LedgerTransaction,
    SellerCustomer,
    SellerNotification,
    SellerSettings,
    TeamMember,
)
from ..permissions import IsSeller
from ..serializers import (
    AddCreditSerializer,
    AdvanceDepositSerializer,
    AdvanceUseSerializer,
    BusinessProfileSerializer,
    FcmTokenSerializer,
    ReceivePaymentSerializer,
    RemindSerializer,
    SellerCustomerCreateSerializer,
    SellerCustomerUpdateSerializer,
    SellerNotificationSerializer,
    SellerSettingsSerializer,
    TeamMemberSerializer,
)
from ..services import (
    activity_item,
    advance_summary,
    customer_detail,
    customer_list_item,
    dashboard_data,
    refresh_overdue_for_seller,
    transaction_item,
)
from ..sync_service import (
    SyncError,
    apply_advance_deposit_idempotent,
    apply_advance_use_idempotent,
    apply_credit_idempotent,
    apply_payment_idempotent,
    create_customer_idempotent,
    parse_since,
    write_result,
)
from ..utils import get_seller_customer, seller_to_dict


class SellerAPIView(APIView):
    authentication_classes = [SellerJWTAuthentication]
    permission_classes = [IsSeller]


def _quota_error_response(exc):
    return Response(
        {
            'message': exc.message,
            'code': exc.code,
            'quota': exc.quota,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _with_quota(payload, seller):
    from ..subscription_service import message_quota_dict

    payload['quota'] = message_quota_dict(seller)
    return payload


def _require_message_quota(seller, count=1):
    from ..subscription_service import SubscriptionQuotaError, assert_can_send_messages

    try:
        assert_can_send_messages(seller, count=count)
    except SubscriptionQuotaError as exc:
        return exc
    return None


class SellerMeView(SellerAPIView):
    def get(self, request):
        from ..subscription_service import start_seller_trial

        start_seller_trial(request.user)
        return Response({'user': seller_to_dict(request.user)})


class SellerDashboardView(SellerAPIView):
    def get(self, request):
        try:
            from ..seller_razorpay_service import sync_seller_payment_links

            sync_seller_payment_links(request.user)
        except Exception:
            pass
        return Response(dashboard_data(request.user))


class SellerCustomersView(SellerAPIView):
    def get(self, request):
        refresh_overdue_for_seller(request.user)
        qs = SellerCustomer.objects.filter(seller=request.user)
        status_filter = request.query_params.get('status')
        search = request.query_params.get('search')
        since = request.query_params.get('since')
        if status_filter and status_filter != 'all':
            if status_filter == 'overdue':
                today = timezone.localdate()
                qs = qs.filter(
                    outstanding_amount__gt=0,
                    next_due_date__lt=today,
                    next_due_date__isnull=False,
                )
            else:
                qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
        if since:
            try:
                qs = qs.filter(updated_at__gte=parse_since(since))
            except SyncError as exc:
                return Response(
                    {'message': exc.message, 'code': exc.code},
                    status=exc.status_code,
                )
        return Response({'customers': [customer_list_item(c) for c in qs]})

    def post(self, request):
        if request.data.get('client_id'):
            try:
                customer, duplicate = create_customer_idempotent(
                    request.user,
                    client_id=request.data.get('client_id'),
                    device_created_at=request.data.get('device_created_at'),
                    name=request.data.get('name', ''),
                    phone=request.data.get('phone', ''),
                    email=request.data.get('email', ''),
                    address=request.data.get('address', ''),
                    city=request.data.get('city', ''),
                    state=request.data.get('state', ''),
                    country=request.data.get('country', 'India'),
                )
            except SyncError as exc:
                return Response(
                    {'message': exc.message, 'code': exc.code},
                    status=exc.status_code,
                )
            return Response(
                {'customer': customer_detail(customer), 'duplicate': duplicate},
                status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED,
            )

        serializer = SellerCustomerCreateSerializer(
            data=request.data, context={'seller': request.user}
        )
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(
            {'customer': customer_detail(customer), 'duplicate': False},
            status=status.HTTP_201_CREATED,
        )


class SellerCustomerDetailView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        return Response({'customer': customer_detail(customer)})

    def put(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        serializer = SellerCustomerUpdateSerializer(
            customer,
            data=request.data,
            partial=True,
            context={'seller': request.user},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'customer': customer_detail(customer)})

    def delete(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        customer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomerTransactionsView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        txs = LedgerTransaction.objects.filter(customer=customer)
        since = request.query_params.get('since')
        if since:
            try:
                txs = txs.filter(updated_at__gte=parse_since(since))
            except SyncError as exc:
                return Response(
                    {'message': exc.message, 'code': exc.code},
                    status=exc.status_code,
                )
        return Response(
            {'transactions': [transaction_item(tx) for tx in txs]}
        )


class CustomerAdvanceView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        return Response({'advance': advance_summary(customer)})


class AdvanceDepositView(SellerAPIView):
    def post(self, request):
        serializer = AdvanceDepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = get_seller_customer(request.user, data['customer_id'])
        try:
            tx, duplicate = apply_advance_deposit_idempotent(
                request.user,
                customer,
                data['amount'],
                client_id=data.get('client_id'),
                device_created_at=data.get('device_created_at'),
                payment_method=data.get('payment_method', 'UPI'),
                note=data.get('note', ''),
            )
        except SyncError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.status_code,
            )
        customer.refresh_from_db()
        payload = write_result(customer, tx, duplicate=duplicate)
        payload['advance'] = advance_summary(customer)
        payload['message'] = 'Advance deposited' if not duplicate else 'Advance deposit already recorded'
        return Response(payload, status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED)


class AdvanceUseView(SellerAPIView):
    def post(self, request):
        serializer = AdvanceUseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = get_seller_customer(request.user, data['customer_id'])
        try:
            tx, duplicate = apply_advance_use_idempotent(
                request.user,
                customer,
                data['amount'],
                client_id=data.get('client_id'),
                device_created_at=data.get('device_created_at'),
                note=data.get('note', ''),
            )
        except SyncError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.status_code,
            )
        customer.refresh_from_db()
        payload = write_result(customer, tx, duplicate=duplicate)
        payload['advance'] = advance_summary(customer)
        payload['message'] = 'Advance used' if not duplicate else 'Advance use already recorded'
        return Response(payload, status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED)


class CustomerNotesView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        messages = get_thread_messages(seller_customer=customer).filter(
            message__gt=''
        )
        return Response(
            {
                'notes': [
                    {
                        'id': str(m.id),
                        'text': m.message,
                        'sender': m.sender,
                        'created_at': m.created_at.isoformat(),
                    }
                    for m in messages
                ]
            }
        )

    def post(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        text = request.data.get('text') or request.data.get('note') or request.data.get('message', '')
        if not text.strip():
            return Response(
                {'message': 'text is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        quota_err = _require_message_quota(request.user, count=1)
        if quota_err:
            return _quota_error_response(quota_err)
        msg = send_seller_message(
            request.user,
            customer,
            text=text,
            request=request,
        )
        return Response(
            _with_quota(message_to_dict(msg, request), request.user),
            status=status.HTTP_201_CREATED,
        )


class CustomerMessagesView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        messages = get_thread_messages(seller_customer=customer)
        return Response(
            {'messages': [message_to_dict(m, request) for m in messages]}
        )

    def post(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        text = request.data.get('message') or request.data.get('text', '')
        if not text.strip():
            return Response(
                {'message': 'message is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        quota_err = _require_message_quota(request.user, count=1)
        if quota_err:
            return _quota_error_response(quota_err)
        msg = send_seller_message(
            request.user,
            customer,
            text=text,
            request=request,
        )
        return Response(
            _with_quota(message_to_dict(msg, request), request.user),
            status=status.HTTP_201_CREATED,
        )


class CustomerFilesView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        messages = get_thread_messages(seller_customer=customer).exclude(attachment='')
        return Response(
            {
                'files': [
                    {
                        'id': str(m.id),
                        'label': m.message or 'Image',
                        'file_url': message_to_dict(m, request)['image_url'],
                        'created_at': m.created_at.isoformat(),
                    }
                    for m in messages
                    if m.attachment
                ]
            }
        )

    def post(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        upload = request.FILES.get('file')
        if not upload:
            return Response(
                {'message': 'file is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        quota_err = _require_message_quota(request.user, count=1)
        if quota_err:
            return _quota_error_response(quota_err)
        label = request.data.get('label') or request.data.get('message', '')
        msg = send_seller_message(
            request.user,
            customer,
            text=label,
            attachment=upload,
            request=request,
        )
        data = message_to_dict(msg, request)
        return Response(
            _with_quota(
                {
                    'id': data['id'],
                    'label': label or 'Image',
                    'file_url': data['image_url'],
                    'message': data,
                    'created_at': data['created_at'],
                },
                request.user,
            ),
            status=status.HTTP_201_CREATED,
        )


class ReceivePaymentView(SellerAPIView):
    def post(self, request):
        serializer = ReceivePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = get_seller_customer(request.user, data['customer_id'])
        try:
            tx, duplicate, sms_result = apply_payment_idempotent(
                request.user,
                customer,
                data['amount'],
                client_id=data.get('client_id'),
                device_created_at=data.get('device_created_at'),
                payment_method=data.get('payment_method', 'UPI'),
                note=data.get('note', ''),
                send_sms=data.get('send_sms'),
            )
        except SyncError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.status_code,
            )
        customer.refresh_from_db()
        payload = write_result(customer, tx, duplicate=duplicate, sms=sms_result)
        payload['message'] = 'Payment received' if not duplicate else 'Payment already recorded'
        return Response(payload, status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED)


class AddCreditView(SellerAPIView):
    def post(self, request):
        serializer = AddCreditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = get_seller_customer(request.user, data['customer_id'])
        try:
            tx, duplicate, sms_result = apply_credit_idempotent(
                request.user,
                customer,
                data['amount'],
                client_id=data.get('client_id'),
                device_created_at=data.get('device_created_at'),
                note=data.get('note', ''),
                send_sms=data.get('send_sms'),
                due_date=data.get('due_date'),
            )
        except SyncError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.status_code,
            )
        customer.refresh_from_db()
        payload = write_result(customer, tx, duplicate=duplicate, sms=sms_result)
        payload['message'] = 'Credit added' if not duplicate else 'Credit already recorded'
        return Response(payload, status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED)


class UnifiedTransactionView(SellerAPIView):
    def post(self, request):
        tx_type = request.data.get('type')
        if tx_type == 'receive':
            return ReceivePaymentView().post(request)
        if tx_type == 'credit':
            return AddCreditView().post(request)
        return Response(
            {'message': 'type must be receive or credit'},
            status=status.HTTP_400_BAD_REQUEST,
        )


class RemindCustomerView(SellerAPIView):
    def post(self, request, customer_id):
        from ..models import ReminderLog
        from ..reminders import resolve_reminder_channels, send_customer_reminder

        customer = get_seller_customer(request.user, customer_id)
        if customer.outstanding_amount <= 0:
            return Response(
                {
                    'message': 'Customer has no outstanding balance to remind.',
                    'code': 'no_outstanding',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = RemindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channels = resolve_reminder_channels(
            request.user,
            serializer.validated_data.get('channels'),
        )
        quota_err = _require_message_quota(request.user, count=len(channels))
        if quota_err:
            return _quota_error_response(quota_err)
        results = send_customer_reminder(
            request.user,
            customer,
            channels=channels,
            reminder_type=ReminderLog.TYPE_MANUAL,
        )
        any_sent = any(r.get('sent') for r in results.values())
        return Response(
            _with_quota(
                {
                    'message': 'Reminder sent' if any_sent else 'Reminder queued with errors',
                    **results,
                },
                request.user,
            ),
            status=status.HTTP_200_OK,
        )


class CallLogView(SellerAPIView):
    def post(self, request, customer_id):
        customer = get_seller_customer(request.user, customer_id)
        CallLog.objects.create(customer=customer, seller=request.user)
        return Response({'message': 'Call logged'}, status=status.HTTP_201_CREATED)


class SettingsView(SellerAPIView):
    def get(self, request):
        settings, _ = SellerSettings.objects.get_or_create(seller=request.user)
        return Response(SellerSettingsSerializer(settings).data)

    def put(self, request):
        settings, _ = SellerSettings.objects.get_or_create(seller=request.user)
        serializer = SellerSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(SellerSettingsSerializer(settings).data)


class BusinessView(SellerAPIView):
    def get(self, request):
        return Response(BusinessProfileSerializer(request.user).data)

    def put(self, request):
        serializer = BusinessProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(BusinessProfileSerializer(request.user).data)


class TeamView(SellerAPIView):
    def get(self, request):
        members = TeamMember.objects.filter(seller=request.user)
        return Response(
            {'team': TeamMemberSerializer(members, many=True).data}
        )

    def post(self, request):
        serializer = TeamMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = serializer.save(seller=request.user)
        return Response(
            TeamMemberSerializer(member).data,
            status=status.HTTP_201_CREATED,
        )


class SellerNotificationsListView(SellerAPIView):
    def get(self, request):
        notifications = SellerNotification.objects.filter(seller=request.user)
        return Response(
            {'notifications': SellerNotificationSerializer(notifications, many=True).data}
        )


class SellerUnreadNotificationCountView(SellerAPIView):
    def get(self, request):
        count = SellerNotification.objects.filter(
            seller=request.user, is_read=False
        ).count()
        return Response({'unread_count': count})


class SellerNotificationReadView(SellerAPIView):
    def patch(self, request, notification_id):
        notification = get_object_or_404(
            SellerNotification, id=notification_id, seller=request.user
        )
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(SellerNotificationSerializer(notification).data)


class SellerNotificationsReadAllView(SellerAPIView):
    def patch(self, request):
        updated = SellerNotification.objects.filter(
            seller=request.user,
            is_read=False,
        ).update(is_read=True)
        return Response({'message': 'All notifications marked read', 'updated': updated})


class SellerFcmTokenView(SellerAPIView):
    def post(self, request):
        serializer = FcmTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        register_seller_device_token(request.user, **serializer.validated_data)
        return Response({'message': 'FCM token registered'}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        token = request.data.get('token', '')
        unregister_seller_device_token(request.user, token=token)
        return Response({'message': 'FCM token unregistered'})


class SellerPaymentMethodsView(SellerAPIView):
    def get(self, request):
        return Response(
            {
                'methods': [
                    {
                        'id': 'cash',
                        'label': 'Cash',
                        'seller_manual': True,
                        'online': False,
                    },
                    {
                        'id': 'my_qr',
                        'label': 'My QR',
                        'seller_manual': True,
                        'online': False,
                    },
                    {
                        'id': 'online',
                        'label': 'UPI / Card / Wallet / Net Banking',
                        'online': True,
                        'seller_manual': False,
                    },
                    {
                        'id': 'payment_link',
                        'label': 'Payment link',
                        'online': True,
                        'seller_manual': False,
                    },
                ],
                'partial_payment_allowed': True,
                'online_gateway': 'razorpay',
            }
        )


class SellerRazorpayConfigView(SellerAPIView):
    def get(self, request):
        from django.conf import settings

        from customerapp.razorpay_service import razorpay_configured
        from easyudhar.payment_utils import payment_methods_catalog
        from easyudhar.razorpay_config import get_razorpay_credentials

        key_id, _, _ = get_razorpay_credentials()
        return Response(
            {
                'configured': razorpay_configured(),
                'key_id': key_id or None,
                'mode': settings.RAZORPAY_MODE,
                'methods': payment_methods_catalog(online=True),
                'partial_payment_allowed': True,
            }
        )


class SellerCustomerRazorpayCreateOrderView(SellerAPIView):
    def post(self, request, customer_id):
        from customerapp.razorpay_service import RazorpayError

        from ..seller_razorpay_service import create_seller_razorpay_order

        customer = get_seller_customer(request.user, customer_id)
        amount = request.data.get('amount') or request.data.get('total')
        note = request.data.get('note', '')
        if not amount:
            return Response(
                {'message': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payload = create_seller_razorpay_order(
                seller=request.user,
                customer=customer,
                amount=amount,
                note=note,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class SellerCustomerRazorpayVerifyView(SellerAPIView):
    def post(self, request, customer_id):
        from customerapp.razorpay_service import RazorpayError

        from ..seller_razorpay_service import verify_and_settle_seller_payment

        customer = get_seller_customer(request.user, customer_id)
        order_id = (
            request.data.get('razorpay_order_id')
            or request.data.get('order_id')
            or request.data.get('razorpayOrderId')
        )
        payment_id = (
            request.data.get('razorpay_payment_id')
            or request.data.get('payment_id')
            or request.data.get('razorpayPaymentId')
        )
        signature = (
            request.data.get('razorpay_signature')
            or request.data.get('signature')
            or request.data.get('razorpaySignature')
        )
        if not order_id or not payment_id or not signature:
            return Response(
                {
                    'message': 'razorpay_order_id, razorpay_payment_id, and razorpay_signature are required.',
                    'code': 'missing_fields',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payload = verify_and_settle_seller_payment(
                seller=request.user,
                customer=customer,
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=signature,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_200_OK)


class SellerCustomerPaymentLinkCreateView(SellerAPIView):
    def post(self, request, customer_id):
        from customerapp.razorpay_service import RazorpayError

        from ..seller_razorpay_service import create_seller_payment_link

        customer = get_seller_customer(request.user, customer_id)
        amount = request.data.get('amount') or request.data.get('max_amount')
        note = request.data.get('note', '')
        if not amount:
            return Response(
                {'message': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payload = create_seller_payment_link(
                seller=request.user,
                customer=customer,
                max_amount=amount,
                note=note,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class SellerCustomerPaymentLinksSyncView(SellerAPIView):
    def post(self, request, customer_id):
        from customerapp.razorpay_service import RazorpayError

        from ..seller_razorpay_service import sync_customer_payment_links

        customer = get_seller_customer(request.user, customer_id)
        try:
            payload = sync_customer_payment_links(
                seller=request.user,
                customer=customer,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_200_OK)

