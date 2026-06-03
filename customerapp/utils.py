from rest_framework_simplejwt.tokens import RefreshToken

from .models import Customer


def tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access_token': str(refresh.access_token),
        'refresh_token': str(refresh),
    }


def customer_to_dict(user):
    return {
        'id': user.id,
        'name': user.full_name,
        'email': user.email,
        'mobile': user.phone,
        'role': user.role,
        'avatar_initials': user.avatar_initials,
    }
