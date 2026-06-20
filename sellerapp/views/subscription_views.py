from rest_framework import status
from rest_framework.response import Response

from customerapp.razorpay_service import RazorpayError

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
