from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..apple_iap import AppleIapError, handle_app_store_notification, verify_and_grant
from .seller_views import SellerAPIView


class SellerIapVerifyView(SellerAPIView):
    def post(self, request):
        data = request.data or {}
        try:
            result = verify_and_grant(
                seller=request.user,
                platform=data.get('platform') or 'ios',
                product_id=data.get('product_id') or '',
                transaction_id=data.get('transaction_id') or '',
                signed_transaction=data.get('signed_transaction') or '',
            )
        except AppleIapError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.http_status,
            )
        return Response(result)


class AppleIapNotificationView(APIView):
    """App Store Server Notifications V2. Verified via JWS, no seller JWT."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data or {}
        signed = data.get('signedPayload') or data.get('signed_payload') or ''
        try:
            result = handle_app_store_notification(signed)
        except AppleIapError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)
