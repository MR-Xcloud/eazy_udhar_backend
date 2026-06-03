from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..device_tokens import register_customer_device_token, unregister_customer_device_token
from ..models import (
    CustomerAccount,
    CustomerNotification,
    CustomerPayment,
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
from ..services import dashboard_summary, payment_summary, process_payment
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
        qs = CustomerAccount.objects.filter(user=request.user)
        limit = request.query_params.get('limit')
        if limit:
            try:
                qs = qs[: int(limit)]
            except ValueError:
                pass
        serializer = CustomerAccountSerializer(qs, many=True)
        return Response({'accounts': serializer.data})


class AccountStatementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        account = get_object_or_404(CustomerAccount, id=shop_id, user=request.user)
        lines = account.statement_lines.all()
        return Response(
            {
                'shop_id': str(account.id),
                'shop_name': account.shop_name,
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
            return Response({'messages': []})

        messages = get_thread_messages(seller_customer=account.seller_customer)
        return Response(
            {'messages': [message_to_dict(m, request) for m in messages]}
        )

    def post(self, request, shop_id):
        try:
            account = resolve_account_for_shop(request.user, shop_id)
        except CustomerAccount.DoesNotExist:
            return Response({'message': 'Shop not found.'}, status=status.HTTP_404_NOT_FOUND)

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

    def post(self, request):
        shop_id = request.data.get('shopId') or request.data.get('shop_id')
        shop_ids = request.data.get('shopIds') or request.data.get('shop_ids') or []
        amount = request.data.get('amount') or request.data.get('total')
        method = request.data.get('method', 'upi')

        if not amount:
            return Response(
                {'message': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, TypeError):
            return Response(
                {'message': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = None
        if shop_id and not shop_ids:
            account = get_object_or_404(CustomerAccount, id=shop_id, user=request.user)
            shop_ids = [shop_id]

        try:
            payments, reference_id = process_payment(
                request.user,
                shop_ids=shop_ids,
                amount=amount,
                method=method,
                account=account,
            )
        except ValueError as exc:
            return Response({'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'message': 'Payment successful',
                'reference_id': reference_id,
                'payments': PaymentSerializer(payments, many=True).data,
            },
            status=status.HTTP_201_CREATED,
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
                        'answer': 'Go to Pay, select shops, choose a payment method, and confirm.',
                    },
                    {
                        'question': 'How do I download a statement?',
                        'answer': 'Open an account and tap Statement to view transaction history.',
                    },
                    {
                        'question': 'Who do I contact for support?',
                        'answer': 'Email support@easyudhar.com or chat with your shop from Accounts.',
                    },
                ],
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
