from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from easyudhar.jwt_serializers import build_token_refresh_serializer
from ..models import AdminUser
from ..serializers import AdminLoginSerializer
from ..utils import admin_user_to_dict
from .base import AdminAPIView


def tokens_for_admin(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


class AdminLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        return Response(
            {
                **tokens_for_admin(user),
                'user': admin_user_to_dict(user),
            },
            status=status.HTTP_200_OK,
        )


class AdminMeView(AdminAPIView):
    def get(self, request):
        return Response(admin_user_to_dict(request.user))


class AdminTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = build_token_refresh_serializer(AdminUser)

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            data = response.data
            payload = {'access': data.get('access')}
            if data.get('refresh'):
                payload['refresh'] = data['refresh']
            return Response(payload, status=status.HTTP_200_OK)
        return response


class AdminLogoutView(AdminAPIView):
    def post(self, request):
        refresh = request.data.get('refresh')
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except Exception:
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)
