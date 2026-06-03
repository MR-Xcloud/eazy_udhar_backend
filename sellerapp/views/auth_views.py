from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from ..authentication import SellerJWTAuthentication
from ..permissions import IsSeller
from ..serializers import (
    ForgotPasswordSerializer,
    SellerLoginSerializer,
    SellerRegisterSerializer,
)
from ..utils import seller_to_dict, tokens_for_seller


class SellerRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SellerRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'message': 'Registration successful',
                'user': seller_to_dict(user),
                **tokens_for_seller(user),
            },
            status=status.HTTP_201_CREATED,
        )


class SellerLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SellerLoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        return Response(
            {
                'message': 'Login successful',
                'user': seller_to_dict(user),
                **tokens_for_seller(user),
            },
            status=status.HTTP_200_OK,
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {'message': 'If the email exists, password reset instructions were sent.'},
            status=status.HTTP_200_OK,
        )


class SellerTokenRefreshView(TokenRefreshView):
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
    authentication_classes = [SellerJWTAuthentication]
    permission_classes = [IsSeller]

    def post(self, request):
        refresh = request.data.get('refresh_token')
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except Exception:
                pass
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)
