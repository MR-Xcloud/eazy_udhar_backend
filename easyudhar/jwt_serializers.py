"""JWT refresh serializers for non-AUTH_USER_MODEL accounts (Seller, AdminUser)."""

from typing import Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings


def build_token_refresh_serializer(user_model):
    """Build a TokenRefreshSerializer that validates tokens for the given model."""

    class AppTokenRefreshSerializer(TokenRefreshSerializer):
        def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
            refresh = attrs.get('refresh') or attrs.get('refresh_token')
            if not refresh:
                raise AuthenticationFailed(
                    self.error_messages['no_active_account'],
                    'no_active_account',
                )

            refresh = self.token_class(refresh)

            user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
            if user_id:
                try:
                    user = user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
                except user_model.DoesNotExist:
                    raise AuthenticationFailed(
                        self.error_messages['no_active_account'],
                        'no_active_account',
                    )
                if not api_settings.USER_AUTHENTICATION_RULE(user):
                    raise AuthenticationFailed(
                        self.error_messages['no_active_account'],
                        'no_active_account',
                    )

            data = {'access': str(refresh.access_token)}

            if api_settings.ROTATE_REFRESH_TOKENS:
                if api_settings.BLACKLIST_AFTER_ROTATION:
                    try:
                        refresh.blacklist()
                    except AttributeError:
                        pass

                refresh.set_jti()
                refresh.set_exp()
                refresh.set_iat()
                refresh.outstand()

                data['refresh'] = str(refresh)

            return data

    return AppTokenRefreshSerializer
