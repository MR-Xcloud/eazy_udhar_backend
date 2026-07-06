from rest_framework import status
from rest_framework.response import Response

from customerapp.razorpay_service import RazorpayError

from ..sms_pack_service import (
    create_sms_pack_order,
    list_active_sms_packs,
    verify_sms_pack_payment,
)
from ..subscription_service import (
    create_subscription_order,
    list_purchasable_plans,
    subscription_status_payload,
    verify_subscription_payment,
)
from .seller_views import SellerAPIView


class SellerSubscriptionStatusView(SellerAPIView):
    def get(self, request):
        from ..subscription_service import start_seller_trial

        start_seller_trial(request.user)
        return Response(
            {
                'subscription': subscription_status_payload(request.user),
            }
        )


class SellerSubscriptionPlansView(SellerAPIView):
    def get(self, request):
        return Response({'plans': list_purchasable_plans()})


class SellerSubscriptionCreateOrderView(SellerAPIView):
    def post(self, request):
        plan_slug = request.data.get('plan_slug') or request.data.get('plan')
        billing_cycle = request.data.get('billing_cycle', 'monthly')
        try:
            payload = create_subscription_order(
                seller=request.user,
                plan_slug=plan_slug,
                billing_cycle=billing_cycle,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class SellerSubscriptionVerifyView(SellerAPIView):
    def post(self, request):
        data = request.data
        try:
            result = verify_subscription_payment(
                seller=request.user,
                plan_slug=data.get('plan_slug') or data.get('plan'),
                billing_cycle=data.get('billing_cycle', 'monthly'),
                razorpay_order_id=data.get('razorpay_order_id', ''),
                razorpay_payment_id=data.get('razorpay_payment_id', ''),
                razorpay_signature=data.get('razorpay_signature', ''),
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


class SellerSmsPacksView(SellerAPIView):
    def get(self, request):
        return Response({'packs': list_active_sms_packs()})


class SellerSmsPackCreateOrderView(SellerAPIView):
    def post(self, request):
        pack_slug = request.data.get('pack_slug') or request.data.get('slug')
        try:
            payload = create_sms_pack_order(
                seller=request.user,
                pack_slug=pack_slug,
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class SellerSmsPackVerifyView(SellerAPIView):
    def post(self, request):
        data = request.data
        try:
            result = verify_sms_pack_payment(
                seller=request.user,
                pack_slug=data.get('pack_slug') or data.get('slug'),
                razorpay_order_id=data.get('razorpay_order_id', ''),
                razorpay_payment_id=data.get('razorpay_payment_id', ''),
                razorpay_signature=data.get('razorpay_signature', ''),
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)

