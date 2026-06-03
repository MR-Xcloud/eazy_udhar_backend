from customerapp.models import CustomerDeviceToken


def register_customer_device_token(user, *, token, platform, device_id=''):
    token = (token or '').strip()
    if not token:
        raise ValueError('token is required')

    device, created = CustomerDeviceToken.objects.update_or_create(
        token=token,
        defaults={
            'user': user,
            'platform': platform,
            'device_id': device_id or '',
            'is_active': True,
        },
    )
    return device, created


def unregister_customer_device_token(user, *, token=''):
    qs = CustomerDeviceToken.objects.filter(user=user, is_active=True)
    if token:
        qs = qs.filter(token=token.strip())
    return qs.update(is_active=False)
