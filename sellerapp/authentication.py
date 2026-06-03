from django.contrib.auth.backends import ModelBackend
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings

from .models import Seller


class SellerBackend(ModelBackend):
    """Authenticate seller users (not AUTH_USER_MODEL)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = kwargs.get('email') or username
        if not email or not password:
            return None
        try:
            seller = Seller.objects.get(email=email)
        except Seller.DoesNotExist:
            return None
        if seller.check_password(password) and self.user_can_authenticate(seller):
            return seller
        return None

    def get_user(self, user_id):
        try:
            return Seller.objects.get(pk=user_id)
        except Seller.DoesNotExist:
            return None


class SellerJWTAuthentication(JWTAuthentication):
    """Load Seller from JWT user id (Seller is not AUTH_USER_MODEL)."""

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as exc:
            raise InvalidToken(
                'Token contained no recognizable user identification'
            ) from exc

        try:
            user = Seller.objects.get(pk=user_id)
        except Seller.DoesNotExist as exc:
            raise AuthenticationFailed('Seller not found', code='user_not_found') from exc

        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed('User is inactive', code='user_inactive')

        return user
