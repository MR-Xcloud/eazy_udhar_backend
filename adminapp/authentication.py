from django.contrib.auth.backends import ModelBackend
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings

from .models import AdminUser


class AdminBackend(ModelBackend):
    """Authenticate admin users (not AUTH_USER_MODEL)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = kwargs.get('email') or username
        if not email or not password:
            return None
        try:
            admin = AdminUser.objects.get(email=email)
        except AdminUser.DoesNotExist:
            return None
        if admin.check_password(password) and self.user_can_authenticate(admin):
            return admin
        return None

    def get_user(self, user_id):
        try:
            return AdminUser.objects.get(pk=user_id)
        except AdminUser.DoesNotExist:
            return None


class AdminJWTAuthentication(JWTAuthentication):
    """Load AdminUser from JWT user id (AdminUser is not AUTH_USER_MODEL)."""

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken(
                'Token contained no recognizable user identification'
            ) from exc

        try:
            user = AdminUser.objects.get(pk=user_id)
        except AdminUser.DoesNotExist as exc:
            raise AuthenticationFailed('Admin user not found', code='user_not_found') from exc

        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed('User is inactive', code='user_inactive')

        return user
