from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import RazorpayPaymentOrder
from ..razorpay_service import (
    RazorpayError,
    create_razorpay_order,
    handle_razorpay_webhook,
    razorpay_configured,
    verify_and_settle_payment,
)
from ..serializers import PaymentSerializer


from easyudhar.payment_utils import payment_methods_catalog


class PaymentMethodsCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        online = request.query_params.get('online', '').lower() in ('1', 'true', 'yes')
        return Response(
            {
                'methods': payment_methods_catalog(online=online),
                'partial_payment_allowed': True,
                'online_gateway': 'razorpay',
            }
        )


class RazorpayCreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not razorpay_configured():
            return Response(
                {
                    'message': 'Razorpay is not configured on the server.',
                    'code': 'razorpay_not_configured',
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        shop_id = request.data.get('shopId') or request.data.get('shop_id')
        shop_ids = request.data.get('shopIds') or request.data.get('shop_ids') or []
        amount = request.data.get('amount') or request.data.get('total')

        if not amount:
            return Response({'message': 'amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, TypeError):
            return Response({'message': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = create_razorpay_order(
                user=request.user,
                shop_id=shop_id,
                shop_ids=shop_ids,
                amount=amount,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(payload, status=status.HTTP_201_CREATED)


class RazorpayVerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
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
            payments, reference_id = verify_and_settle_payment(
                user=request.user,
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature=signature,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'message': 'Payment successful',
                'reference_id': reference_id,
                'payments': PaymentSerializer(payments, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class RazorpayWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get('X-Razorpay-Signature', '')
        if not signature:
            return Response({'message': 'Missing signature'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = handle_razorpay_webhook(request.body, signature)
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(result, status=status.HTTP_200_OK)


class RazorpayConfigView(APIView):
    """Public key + mode for mobile/web checkout initialization."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings

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
