from rest_framework_simplejwt.tokens import RefreshToken

import uuid

from django.http import Http404

from .models import Seller, SellerCustomer

LOCAL_ID_PREFIX = 'local:'


def tokens_for_seller(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access_token': str(refresh.access_token),
        'refresh_token': str(refresh),
    }


def seller_to_dict(user):
    from .subscription_service import subscription_status_payload

    return {
        'id': str(user.id),
        'name': user.full_name,
        'email': user.email,
        'mobile': user.phone,
        'business_name': user.business_name,
        'role': user.role,
        'subscription': subscription_status_payload(user),
    }


def format_inr(amount):
    value = float(amount)
    return f'Rs. {value:,.0f}'.replace(',', ',')


def format_inr_signed(amount, positive=True):
    prefix = '+' if positive else '-'
    return f'{prefix}{format_inr(abs(amount))}'


def normalize_phone(phone):
    """Digits only; last 10 digits for Indian numbers."""
    if not phone:
        return ''
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def seller_customer_phone_exists(seller, phone, exclude_id=None):
    norm = normalize_phone(phone)
    if not norm:
        return False
    qs = SellerCustomer.objects.filter(seller=seller)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    for customer in qs.only('id', 'phone'):
        if normalize_phone(customer.phone) == norm:
            return True
    return False


def normalize_client_id(value):
    """Strip Flutter offline prefix: local:<uuid> -> <uuid>."""
    if value is None:
        return ''
    text = str(value).strip()
    if text.lower().startswith(LOCAL_ID_PREFIX):
        text = text[len(LOCAL_ID_PREFIX):]
    return text


def parse_client_uuid(value, *, required=False):
    text = normalize_client_id(value)
    if not text:
        if required:
            raise ValueError('client_id must be a valid UUID.')
        return None
    try:
        return uuid.UUID(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('client_id must be a valid UUID.') from exc


def get_seller_customer(seller, customer_ref):
    """Resolve customer by server id or offline client_id (with optional local: prefix)."""
    normalized = normalize_client_id(customer_ref)
    if not normalized:
        raise Http404('Customer not found')

    try:
        uid = uuid.UUID(normalized)
    except (ValueError, TypeError) as exc:
        raise Http404('Customer not found') from exc

    customer = SellerCustomer.objects.filter(seller=seller, id=uid).first()
    if customer:
        return customer

    customer = SellerCustomer.objects.filter(seller=seller, client_id=uid).first()
    if customer:
        return customer

    raise Http404('Customer not found')
