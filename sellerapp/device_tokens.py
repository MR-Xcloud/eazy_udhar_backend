from sellerapp.models import SellerDeviceToken


def register_seller_device_token(seller, *, token, platform, device_id=''):
    token = (token or '').strip()
    if not token:
        raise ValueError('token is required')

    device, created = SellerDeviceToken.objects.update_or_create(
        token=token,
        defaults={
            'seller': seller,
            'platform': platform,
            'device_id': device_id or '',
            'is_active': True,
        },
    )
    return device, created


def unregister_seller_device_token(seller, *, token=''):
    qs = SellerDeviceToken.objects.filter(seller=seller, is_active=True)
    if token:
        qs = qs.filter(token=token.strip())
    return qs.update(is_active=False)
