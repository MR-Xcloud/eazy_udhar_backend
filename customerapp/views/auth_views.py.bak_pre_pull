from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from ..serializers import (
    ForgotPasswordSerializer,
    GoogleSignInSerializer,
    LoginSerializer,
    OTPVerifySerializer,
    OTPSendSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
)
from ..utils import customer_to_dict, tokens_for_user
from ..messaging import sync_customer_from_seller_ledgers


class CustomerRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        sync_customer_from_seller_ledgers(user)
        return Response(
            {
                'message': 'Registration successful',
                'user': customer_to_dict(user),
                **tokens_for_user(user),
            },
            status=status.HTTP_201_CREATED,
        )


class CustomerLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        sync_customer_from_seller_ledgers(user)
        return Response(
            {
                'message': 'Login successful',
                'user': customer_to_dict(user),
                **tokens_for_user(user),
            },
            status=status.HTTP_200_OK,
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.save()
        payload = {'message': 'If the email exists, an OTP has been sent.'}
        if request.data.get('debug') and otp:
            payload['otp'] = otp
        return Response(payload, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'message': 'Password reset successful.'}, status=status.HTTP_200_OK)


class GoogleSignInView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleSignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class OTPSendView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.save()
        delivery = getattr(serializer, 'delivery_result', None) or {}
        payload = {
            'message': delivery.get('message') or (
                'OTP sent to your email.' if delivery.get('sent') else 'OTP generated.'
            ),
            'email': delivery,
        }
        if request.data.get('debug'):
            payload['otp'] = otp
        if delivery and not delivery.get('sent'):
            return Response(
                {
                    **payload,
                    'message': delivery.get('error') or 'OTP could not be sent via email.',
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(payload, status=status.HTTP_200_OK)


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': 'OTP verified',
                'user': customer_to_dict(user),
                **tokens_for_user(user),
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshAPIView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            data = response.data
            return Response(
                {
                    'access_token': data.get('access'),
                    'refresh_token': data.get('refresh', request.data.get('refresh')),
                },
                status=status.HTTP_200_OK,
            )
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh = request.data.get('refresh_token')
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except Exception:
                pass
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)
