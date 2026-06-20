from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..device_tokens import register_customer_device_token, unregister_customer_device_token
from ..models import (
    CustomerAccount,
    CustomerNotification,
    CustomerSettings,
    PaymentMethod,
    ShopMessage,
)
from ..messaging import (
    get_thread_messages,
    message_to_dict,
    resolve_account_for_shop,
    send_customer_message,
    sync_customer_from_seller_ledgers,
)
from ..serializers import (
    ChatMessageSerializer,
    CustomerAccountSerializer,
    FcmTokenSerializer,
    NotificationSerializer,
    PaymentMethodSerializer,
    PaymentSerializer,
    ProfileSerializer,
    SettingsSerializer,
    StatementLineSerializer,
)
from ..services import dashboard_summary, payment_history, payment_summary
from ..sync_service import CustomerSyncError, parse_since, pull_customer_changes
from sellerapp.services import advance_summary
from ..utils import customer_to_dict


class CustomerMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'user': customer_to_dict(request.user)})


class CustomerDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sync_customer_from_seller_ledgers(request.user)
        return Response(dashboard_summary(request.user))


class CustomerAccountsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sync_customer_from_seller_ledgers(request.user)
        qs = CustomerAccount.objects.filter(user=request.user).select_related(
            'seller', 'seller_customer__seller'
        )
        since = request.query_params.get('since')
        if since:
            try:
                qs = qs.filter(updated_at__gte=parse_since(since))
            except CustomerSyncError as exc:
                return Response(
                    {'message': exc.message, 'code': exc.code},
                    status=exc.status_code,
                )
        limit = request.query_params.get('limit')
        if limit:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = CustomerAccountSerializer(qs, many=True)
        return Response({'accounts': serializer.data})


class CustomerSyncChangesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sync_customer_from_seller_ledgers(request.user)
        since = request.query_params.get('since', '')
        try:
            data = pull_customer_changes(request.user, since=since or None)
        except CustomerSyncError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.status_code,
            )
        return Response(data, status=status.HTTP_200_OK)


class CustomerAccountAdvanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        account = get_object_or_404(CustomerAccount, id=shop_id, user=request.user)
        return Response({'advance': advance_summary(account)})


class AccountStatementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        account = get_object_or_404(CustomerAccount, id=shop_id, user=request.user)
        lines = account.statement_lines.all()
        return Response(
            {
                'shop_id': str(account.id),
                'shop_name': account.shop_name,
                'customer_name': request.user.full_name or request.user.email,
                'outstanding_amount': str(account.outstanding_amount),
                'statement': StatementLineSerializer(lines, many=True).data,
            }
        )


class UnreadNotificationCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = CustomerNotification.objects.filter(
            user=request.user, is_read=False
        ).count()
        return Response({'unread_count': count})


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        try:
            account = resolve_account_for_shop(request.user, shop_id)
        except CustomerAccount.DoesNotExist:
            return Response({'message': 'Shop not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not account.seller_customer:
            return Response({'messages': [], 'transactions': []})

        messages = get_thread_messages(seller_customer=account.seller_customer)
        from sellerapp.models import LedgerTransaction
        from sellerapp.services import transaction_item

        txs = LedgerTransaction.objects.filter(
            customer=account.seller_customer
        ).order_by('created_at')
        return Response(
            {
                'messages': [message_to_dict(m, request) for m in messages],
                'transactions': [transaction_item(tx) for tx in txs],
            }
        )

    def post(self, request, shop_id):
        try:
            account = resolve_account_for_shop(request.user, shop_id)
        except CustomerAccount.DoesNotExist:
            return Response({'message': 'Shop not found.'}, status=status.HTTP_404_NOT_FOUND)

        upload = request.FILES.get('file')
        text = (request.data.get('message') or '').strip()

        if upload:
            try:
                msg = send_customer_message(
                    request.user,
                    account,
                    text=text,
                    attachment=upload,
                    request=request,
                )
            except ValueError as exc:
                return Response({'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(
                message_to_dict(msg, request),
                status=status.HTTP_201_CREATED,
            )

        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data.get('message', '')
        if not text.strip():
            return Response(
                {'message': 'message is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            msg = send_customer_message(
                request.user,
                account,
                text=text,
                request=request,
            )
        except ValueError as exc:
            return Response({'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            message_to_dict(msg, request),
            status=status.HTTP_201_CREATED,
        )


class CustomerPaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        shop_id = request.query_params.get('shop_id') or request.query_params.get('shopId')
        method = request.query_params.get('method')
        page = request.query_params.get('page', 1)
        page_size = request.query_params.get('page_size', 25)
        return Response(
            payment_history(
                request.user,
                page=page,
                page_size=page_size,
                shop_id=shop_id,
                method=method,
            )
        )

    def post(self, request):
        return Response(
            {
                'message': (
                    'Direct payments are disabled. Use Razorpay checkout: '
                    'POST /sapp/customer/payments/create-order, then '
                    'POST /sapp/customer/payments/verify after payment.'
                ),
                'code': 'razorpay_required',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class PaymentSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(payment_summary(request.user))


class PaymentMethodsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        methods = PaymentMethod.objects.filter(user=request.user)
        return Response({'methods': PaymentMethodSerializer(methods, many=True).data})

    def post(self, request):
        serializer = PaymentMethodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        method = serializer.save(user=request.user)
        if request.data.get('is_default'):
            PaymentMethod.objects.filter(user=request.user).exclude(id=method.id).update(
                is_default=False
            )
            method.is_default = True
            method.save(update_fields=['is_default'])
        return Response(
            PaymentMethodSerializer(method).data,
            status=status.HTTP_201_CREATED,
        )


class NotificationsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = CustomerNotification.objects.filter(user=request.user)
        return Response(
            {'notifications': NotificationSerializer(notifications, many=True).data}
        )


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id):
        notification = get_object_or_404(
            CustomerNotification, id=notification_id, user=request.user
        )
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)


class NotificationsReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        updated = CustomerNotification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True)
        return Response({'message': 'All notifications marked read', 'updated': updated})


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def put(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProfileSerializer(request.user).data)


class SettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings, _ = CustomerSettings.objects.get_or_create(user=request.user)
        return Response(SettingsSerializer(settings).data)

    def put(self, request):
        settings, _ = CustomerSettings.objects.get_or_create(user=request.user)
        serializer = SettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(SettingsSerializer(settings).data)


class HelpView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                'faq': [
                    {
                        'question': 'How do I pay my shop dues?',
                        'answer': (
                            'Tap the orange + button on the home screen, select the shops '
                            'you want to pay, choose UPI or another method, and confirm.'
                        ),
                    },
                    {
                        'question': 'How do I download a statement?',
                        'answer': (
                            'Open Accounts, pick a shop, then tap Statement. You can share '
                            'or download the PDF from there.'
                        ),
                    },
                    {
                        'question': 'What is wallet balance / advance?',
                        'answer': (
                            'If you pay more than your due amount, the extra is kept as advance '
                            'in your wallet and used automatically on your next purchase.'
                        ),
                    },
                    {
                        'question': 'How do I chat with my shop?',
                        'answer': (
                            'Go to Accounts or Home, open a shop, and tap Chat. You can send '
                            'text messages and photos.'
                        ),
                    },
                    {
                        'question': 'How do privacy settings work?',
                        'answer': (
                            'In Profile → Privacy & security you can choose whether linked shops '
                            'can see your phone number and email on your profile.'
                        ),
                    },
                    {
                        'question': 'Who do I contact for support?',
                        'answer': (
                            'Email support@easyudhar.com or use Help & support in Profile. '
                            'You can also chat with your shop directly from Accounts.'
                        ),
                    },
                ],
                'support_email': 'support@easyudhar.com',
            }
        )


class CustomerFcmTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FcmTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        register_customer_device_token(request.user, **serializer.validated_data)
        return Response({'message': 'FCM token registered'}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        token = request.data.get('token', '')
        unregister_customer_device_token(request.user, token=token)
        return Response({'message': 'FCM token unregistered'})
