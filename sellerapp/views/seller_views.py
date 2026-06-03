from django.db.models import Q
from django.shortcuts import get_object_or_404
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
    CustomerReminder,
    LedgerTransaction,
    SellerCustomer,
    SellerNotification,
    SellerSettings,
    TeamMember,
)
from ..permissions import IsSeller
from ..serializers import (
    AddCreditSerializer,
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
    add_credit,
    customer_detail,
    customer_list_item,
    dashboard_data,
    receive_payment,
    transaction_item,
)
from ..utils import seller_to_dict


class SellerAPIView(APIView):
    authentication_classes = [SellerJWTAuthentication]
    permission_classes = [IsSeller]


class SellerMeView(SellerAPIView):
    def get(self, request):
        return Response({'user': seller_to_dict(request.user)})


class SellerDashboardView(SellerAPIView):
    def get(self, request):
        return Response(dashboard_data(request.user))


class SellerCustomersView(SellerAPIView):
    def get(self, request):
        qs = SellerCustomer.objects.filter(seller=request.user)
        status_filter = request.query_params.get('status')
        search = request.query_params.get('search')
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
        return Response({'customers': [customer_list_item(c) for c in qs]})

    def post(self, request):
        serializer = SellerCustomerCreateSerializer(
            data=request.data, context={'seller': request.user}
        )
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(
            {'customer': customer_detail(customer)},
            status=status.HTTP_201_CREATED,
        )


class SellerCustomerDetailView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        return Response({'customer': customer_detail(customer)})

    def put(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
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
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        customer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomerTransactionsView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        txs = LedgerTransaction.objects.filter(customer=customer)
        return Response(
            {'transactions': [transaction_item(tx) for tx in txs]}
        )


class CustomerNotesView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
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
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        text = request.data.get('text') or request.data.get('note') or request.data.get('message', '')
        if not text.strip():
            return Response(
                {'message': 'text is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        msg = send_seller_message(
            request.user,
            customer,
            text=text,
            request=request,
        )
        return Response(
            message_to_dict(msg, request),
            status=status.HTTP_201_CREATED,
        )


class CustomerMessagesView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        messages = get_thread_messages(seller_customer=customer)
        return Response(
            {'messages': [message_to_dict(m, request) for m in messages]}
        )

    def post(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        text = request.data.get('message') or request.data.get('text', '')
        if not text.strip():
            return Response(
                {'message': 'message is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        msg = send_seller_message(
            request.user,
            customer,
            text=text,
            request=request,
        )
        return Response(
            message_to_dict(msg, request),
            status=status.HTTP_201_CREATED,
        )


class CustomerFilesView(SellerAPIView):
    def get(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
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
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        upload = request.FILES.get('file')
        if not upload:
            return Response(
                {'message': 'file is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
            {
                'id': data['id'],
                'label': label or 'Image',
                'file_url': data['image_url'],
                'message': data,
                'created_at': data['created_at'],
            },
            status=status.HTTP_201_CREATED,
        )


class ReceivePaymentView(SellerAPIView):
    def post(self, request):
        serializer = ReceivePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = get_object_or_404(
            SellerCustomer,
            id=data['customer_id'],
            seller=request.user,
        )
        tx, sms_result = receive_payment(
            request.user,
            customer,
            data['amount'],
            payment_method=data.get('payment_method', 'UPI'),
            note=data.get('note', ''),
            send_sms=data.get('send_sms'),
        )
        return Response(
            {
                'message': 'Payment received',
                'customer': customer_detail(customer),
                'transaction': transaction_item(tx),
                'sms': sms_result,
            },
            status=status.HTTP_201_CREATED,
        )


class AddCreditView(SellerAPIView):
    def post(self, request):
        serializer = AddCreditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = get_object_or_404(
            SellerCustomer,
            id=data['customer_id'],
            seller=request.user,
        )
        tx, sms_result = add_credit(
            request.user,
            customer,
            data['amount'],
            note=data.get('note', ''),
            send_sms=data.get('send_sms'),
        )
        return Response(
            {
                'message': 'Credit added',
                'customer': customer_detail(customer),
                'transaction': transaction_item(tx),
                'sms': sms_result,
            },
            status=status.HTTP_201_CREATED,
        )


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
        from customerapp.messaging import ensure_customer_account, link_seller_customer, notify_customer_event
        from customerapp.models import CustomerNotification

        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
        serializer = RemindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channels = serializer.validated_data['channels']
        message = (
            f'Reminder: {customer.name}, outstanding balance '
            f'{customer.outstanding_amount}. Please pay at earliest.'
        )
        reminder = CustomerReminder.objects.create(
            customer=customer,
            seller=request.user,
            channels=channels,
            message=message,
        )

        customer_user = link_seller_customer(customer)
        if customer_user:
            account = ensure_customer_account(customer, customer_user)
            notify_customer_event(
                customer_user,
                account,
                notification_type=CustomerNotification.TYPE_REMINDER,
                title=f'Reminder from {request.user.business_name}',
                subtitle=message,
                reference_id=str(reminder.id),
            )

        return Response(
            {
                'message': 'Reminder sent',
                'channels': channels,
            },
            status=status.HTTP_200_OK,
        )


class CallLogView(SellerAPIView):
    def post(self, request, customer_id):
        customer = get_object_or_404(
            SellerCustomer, id=customer_id, seller=request.user
        )
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

