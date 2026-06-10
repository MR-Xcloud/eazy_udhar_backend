import random
from datetime import timedelta

from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

from customerapp.messaging import normalize_phone, phones_match
from customerapp.models import Customer, CustomerSettings, OTPRecord


def _generate_otp():
    return f'{random.randint(100000, 999999)}'


def _validate_mobile(phone):
    mobile = normalize_phone(phone)
    if len(mobile) != 10:
        raise ValueError('Enter a valid 10-digit mobile number.')
    return mobile


def _normalize_email(email):
    value = (email or '').strip().lower()
    if not value:
        raise ValueError('Email is required for OTP login.')
    try:
        validate_email(value)
    except ValidationError as exc:
        raise ValueError('Enter a valid email address.') from exc
    return value


def _is_placeholder_email(email):
    if not email:
        return True
    lower = email.lower()
    return lower.endswith('@otp.local') or lower.endswith('@otp.seller.local')


def resolve_customer_email(*, email=None, phone=None):
    if email:
        return _normalize_email(email)
    if phone:
        mobile = _validate_mobile(phone)
        user = find_customer_by_phone(mobile)
        if user and user.email and not _is_placeholder_email(user.email):
            return user.email.lower()
    raise ValueError('Email is required. Provide email or a registered mobile number.')


def resolve_seller_email(*, email=None, phone=None):
    if email:
        return _normalize_email(email)
    if phone:
        mobile = _validate_mobile(phone)
        user = find_seller_by_phone(mobile)
        if user and user.email and not _is_placeholder_email(user.email):
            return user.email.lower()
    raise ValueError('Email is required. Provide email or a registered mobile number.')


def send_login_otp(*, email=None, phone=None, purpose, resolver):
    """Create OTP record and send exactly one email. Returns (otp_code, delivery_result)."""
    from customerapp.email_otp import send_otp_email

    target_email = resolver(email=email, phone=phone)
    mobile = _validate_mobile(phone) if phone else ''
    cooldown_seconds = getattr(settings, 'OTP_RESEND_COOLDOWN_SECONDS', 60)
    now = timezone.now()

    recent = OTPRecord.objects.filter(
        email=target_email,
        purpose=purpose,
        is_verified=False,
        expires_at__gte=now,
    ).order_by('-created_at').first()

    if recent and (now - recent.created_at).total_seconds() < cooldown_seconds:
        return recent.otp_code, {
            'sent': True,
            'channel': 'email',
            'to': target_email,
            'from': settings.DEFAULT_FROM_EMAIL,
            'message_id': '',
            'error': '',
            'already_sent': True,
            'message': 'OTP already sent. Please check your email.',
        }

    OTPRecord.objects.filter(
        email=target_email,
        purpose=purpose,
        is_verified=False,
    ).update(is_verified=True)

    otp = _generate_otp()
    OTPRecord.objects.create(
        phone=mobile,
        email=target_email,
        otp_code=otp,
        purpose=purpose,
        expires_at=now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
    )
    delivery = send_otp_email(to_email=target_email, otp=otp)
    return otp, delivery


def _get_latest_otp_record_by_email(email, purpose, otp_code):
    try:
        record = OTPRecord.objects.filter(
            email=email,
            purpose=purpose,
            is_verified=False,
            expires_at__gte=timezone.now(),
        ).latest('created_at')
    except OTPRecord.DoesNotExist:
        return None
    if record.otp_code != otp_code:
        return None
    return record


def find_customer_by_phone(phone):
    mobile = normalize_phone(phone)
    if not mobile:
        return None
    customer = Customer.objects.filter(phone=mobile).first()
    if customer:
        return customer
    for row in Customer.objects.exclude(phone='').iterator():
        if phones_match(row.phone, mobile):
            return row
    return None


def find_customer_by_email(email):
    return Customer.objects.filter(email__iexact=email).first()


def find_seller_by_phone(phone):
    from sellerapp.models import Seller

    mobile = normalize_phone(phone)
    if not mobile:
        return None
    seller = Seller.objects.filter(phone=mobile).first()
    if seller:
        return seller
    for row in Seller.objects.exclude(phone='').iterator():
        if phones_match(row.phone, mobile):
            return row
    return None


def find_seller_by_email(email):
    from sellerapp.models import Seller

    return Seller.objects.filter(email__iexact=email).first()


def verify_customer_login_otp(*, email=None, phone=None, otp_code):
    target_email = resolve_customer_email(email=email, phone=phone)
    record = _get_latest_otp_record_by_email(target_email, OTPRecord.PURPOSE_LOGIN, otp_code)
    if not record:
        raise ValueError('Invalid or expired OTP.')

    record.is_verified = True
    record.save(update_fields=['is_verified'])

    user = find_customer_by_email(target_email)
    if not user and phone:
        user = find_customer_by_phone(phone)
    if not user:
        mobile = normalize_phone(phone) if phone else ''
        username = target_email
        user = Customer.objects.create(
            username=username,
            email=target_email,
            phone=mobile or '',
            full_name='Customer',
        )
        user.set_unusable_password()
        user.save()
    elif not user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=['password'])

    if phone and not user.phone:
        user.phone = _validate_mobile(phone)
        user.save(update_fields=['phone'])

    CustomerSettings.objects.get_or_create(user=user)
    return user


def verify_seller_login_otp(*, email=None, phone=None, otp_code):
    from sellerapp.models import Seller, SellerSettings

    target_email = resolve_seller_email(email=email, phone=phone)
    record = _get_latest_otp_record_by_email(
        target_email, OTPRecord.PURPOSE_SELLER_LOGIN, otp_code
    )
    if not record:
        raise ValueError('Invalid or expired OTP.')

    record.is_verified = True
    record.save(update_fields=['is_verified'])

    seller = find_seller_by_email(target_email)
    if not seller and phone:
        seller = find_seller_by_phone(phone)
    if not seller:
        mobile = normalize_phone(phone) if phone else ''
        seller = Seller.objects.create(
            username=target_email,
            email=target_email,
            phone=mobile or '',
            full_name='Seller',
            business_name='My Shop',
        )
        seller.set_unusable_password()
        seller.save()
    elif not seller.has_usable_password():
        seller.set_unusable_password()
        seller.save(update_fields=['password'])

    if phone and not seller.phone:
        seller.phone = _validate_mobile(phone)
        seller.save(update_fields=['phone'])

    SellerSettings.objects.get_or_create(seller=seller)
    return seller
