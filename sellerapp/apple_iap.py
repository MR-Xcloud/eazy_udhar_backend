"""Apple In-App Purchase verify + App Store Server Notifications V2."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from urllib.error import URLError
from urllib.request import Request, urlopen

import jwt
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from adminapp.models import SmsPack, SubscriptionPlan
from sellerapp.apple_jws import AppleJwsError, decode_jws_unverified, verify_jws
from sellerapp.excel_report_addon_service import (
    EXCEL_REPORT_ADDON_PLANS,
    excel_report_addon_status,
    extend_excel_report_addon,
)
from sellerapp.models import SellerAppleIapTransaction, SellerSettings
from sellerapp.sms_pack_service import credit_sms_pack_balance
from sellerapp.subscription_service import (
    activate_paid_subscription,
    expire_seller_subscriptions,
    subscription_status_payload,
)

logger = logging.getLogger(__name__)

BUNDLE_ID = 'com.eazyudhar.eazyUdhar'
PRODUCT_PREFIX = 'com.eazyudhar'

RENEW_TYPES = {
    'SUBSCRIBED',
    'DID_RENEW',
    'DID_RECOVER',
    'OFFER_REDEEMED',
    'RENEWAL_EXTENDED',
    'ONE_TIME_CHARGE',
}
REVOKE_TYPES = {
    'EXPIRED',
    'GRACE_PERIOD_EXPIRED',
    'REVOKE',
    'REFUND',
    'REFUND_REVERSED',
}


class AppleIapError(Exception):
    def __init__(self, message, *, code='iap_error', http_status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


def _ms_to_dt(value):
    if value in (None, '', 0):
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        parsed = parse_datetime(str(value))
        return parsed
    return datetime.fromtimestamp(millis / 1000.0, tz=dt_timezone.utc)


def _db_slug(token: str) -> str:
    """App Store IDs use underscores; catalog slugs use hyphens."""
    return (token or '').replace('_', '-')


def parse_product_id(product_id: str) -> dict:
    pid = (product_id or '').strip()
    if pid == f'{PRODUCT_PREFIX}.sub.basic_paid.monthly2':
        return {
            'kind': SellerAppleIapTransaction.KIND_SUBSCRIPTION,
            'plan_slug': 'basic-paid',
            'billing_cycle': 'monthly',
        }

    sub_prefix = f'{PRODUCT_PREFIX}.sub.'
    sms_prefix = f'{PRODUCT_PREFIX}.sms.'
    excel_prefix = f'{PRODUCT_PREFIX}.excel.'

    if pid.startswith(sub_prefix):
        rest = pid[len(sub_prefix) :]
        if rest.endswith('.yearly'):
            slug = _db_slug(rest[: -len('.yearly')])
            cycle = 'yearly'
        elif rest.endswith('.monthly'):
            slug = _db_slug(rest[: -len('.monthly')])
            cycle = 'monthly'
        else:
            raise AppleIapError('Unknown subscription product.', code='unknown_product')
        if not slug or slug == 'basic-free':
            raise AppleIapError('This plan is not purchasable.', code='unknown_product')
        return {
            'kind': SellerAppleIapTransaction.KIND_SUBSCRIPTION,
            'plan_slug': slug,
            'billing_cycle': cycle,
        }

    if pid.startswith(sms_prefix):
        slug = _db_slug(pid[len(sms_prefix) :])
        if not slug:
            raise AppleIapError('Unknown SMS pack product.', code='unknown_product')
        return {
            'kind': SellerAppleIapTransaction.KIND_SMS,
            'plan_slug': slug,
        }

    if pid.startswith(excel_prefix):
        slug = _db_slug(pid[len(excel_prefix) :])
        if slug not in EXCEL_REPORT_ADDON_PLANS:
            raise AppleIapError('Unknown Excel addon product.', code='unknown_product')
        return {
            'kind': SellerAppleIapTransaction.KIND_EXCEL,
            'plan_slug': slug,
            'excel_duration_days': int(EXCEL_REPORT_ADDON_PLANS[slug]['duration_days']),
        }

    raise AppleIapError('Unknown App Store product.', code='unknown_product')


def _allow_unverified_xcode(payload: dict) -> bool:
    env_name = str(payload.get('environment') or '')
    if env_name != 'Xcode':
        return False
    return bool(getattr(settings, 'DEBUG', False) or getattr(settings, 'APPLE_IAP_ALLOW_XCODE', False))


def _app_store_api_token() -> str | None:
    issuer = (getattr(settings, 'APPLE_IAP_ISSUER_ID', '') or '').strip()
    key_id = (getattr(settings, 'APPLE_IAP_KEY_ID', '') or '').strip()
    key_path = (getattr(settings, 'APPLE_IAP_PRIVATE_KEY_PATH', '') or '').strip()
    key_pem = (getattr(settings, 'APPLE_IAP_PRIVATE_KEY', '') or '').strip()
    if not issuer or not key_id or not (key_path or key_pem):
        return None
    if key_path and not key_pem:
        from pathlib import Path

        key_pem = Path(key_path).read_text(encoding='utf-8')
    now = int(datetime.now(tz=dt_timezone.utc).timestamp())
    return jwt.encode(
        {
            'iss': issuer,
            'iat': now,
            'exp': now + 3500,
            'aud': 'appstoreconnect-v1',
            'bid': BUNDLE_ID,
        },
        key_pem,
        algorithm='ES256',
        headers={'kid': key_id, 'typ': 'JWT'},
    )


def _fetch_transaction_from_apple(transaction_id: str) -> dict | None:
    token = _app_store_api_token()
    if not token or not transaction_id:
        return None
    headers = {'Authorization': f'Bearer {token}'}
    for base in (
        'https://api.storekit.itunes.apple.com',
        'https://api.storekit-sandbox.itunes.apple.com',
    ):
        try:
            request = Request(
                f'{base}/inApps/v1/transactions/{transaction_id}',
                headers=headers,
            )
            with urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode('utf-8'))
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
            continue
        signed = (body or {}).get('signedTransactionInfo')
        if signed:
            return verify_jws(signed)
    return None


def verify_signed_transaction(signed_transaction: str, transaction_id: str = '') -> dict:
    raw = (signed_transaction or '').strip()
    if not raw:
        raise AppleIapError('Missing signed_transaction.', code='missing_transaction')

    if raw.count('.') == 2:
        try:
            payload = verify_jws(raw)
        except AppleJwsError as exc:
            unverified = decode_jws_unverified(raw)
            if _allow_unverified_xcode(unverified):
                logger.warning('Accepting Xcode StoreKit transaction without Apple root verify')
                payload = unverified
            else:
                raise AppleIapError(exc.message, code=exc.code) from exc
    else:
        payload = _fetch_transaction_from_apple(transaction_id)
        if payload is None:
            raise AppleIapError(
                'Could not verify this App Store transaction.',
                code='unverified_transaction',
            )

    bundle_id = payload.get('bundleId') or payload.get('bundle_id') or ''
    expected = (getattr(settings, 'APPLE_IAP_BUNDLE_ID', '') or BUNDLE_ID).strip()
    if bundle_id and bundle_id != expected:
        raise AppleIapError('App Store bundle id does not match.', code='bundle_mismatch')

    if payload.get('revocationDate') or payload.get('revocation_date'):
        raise AppleIapError('This App Store transaction was refunded.', code='revoked')

    verified_tx = str(payload.get('transactionId') or payload.get('transaction_id') or '')
    if transaction_id and verified_tx and transaction_id != verified_tx:
        raise AppleIapError(
            'transaction_id does not match the signed transaction.',
            code='transaction_mismatch',
        )
    return payload


def _period_end_for(payload: dict, billing_cycle: str):
    expires = _ms_to_dt(payload.get('expiresDate') or payload.get('expires_date'))
    if expires:
        return expires
    now = timezone.now()
    if billing_cycle == 'yearly':
        return now + timedelta(days=365)
    return now + timedelta(days=30)


def _find_seller_for_original(original_transaction_id: str):
    if not original_transaction_id:
        return None
    row = (
        SellerAppleIapTransaction.objects.filter(
            original_transaction_id=original_transaction_id,
            seller__isnull=False,
        )
        .order_by('-created_at')
        .first()
    )
    return row.seller if row else None


def _payload_result(*, seller, kind, extra=None):
    body = {
        'ok': True,
        'kind': kind,
        'subscription': subscription_status_payload(seller) if seller else None,
    }
    if seller:
        body['addon'] = excel_report_addon_status(seller)
    if extra:
        body.update(extra)
    return body


@transaction.atomic
def grant_verified_transaction(*, seller, payload: dict, notification_uuid: str = ''):
    product_id = str(payload.get('productId') or payload.get('product_id') or '')
    transaction_id = str(payload.get('transactionId') or payload.get('transaction_id') or '')
    original_transaction_id = str(
        payload.get('originalTransactionId')
        or payload.get('original_transaction_id')
        or transaction_id
    )
    if not product_id or not transaction_id:
        raise AppleIapError('Signed transaction is missing product or id.', code='invalid_transaction')

    mapped = parse_product_id(product_id)
    existing = (
        SellerAppleIapTransaction.objects.select_for_update()
        .filter(transaction_id=transaction_id)
        .first()
    )
    if existing:
        if existing.seller_id and seller and existing.seller_id != seller.id:
            raise AppleIapError(
                'This purchase is already linked to another seller.',
                code='already_owned',
                http_status=409,
            )
        if existing.status == SellerAppleIapTransaction.STATUS_GRANTED:
            return _payload_result(
                seller=existing.seller or seller,
                kind=existing.kind,
                extra={'message': 'Purchase already applied', 'idempotent': True},
            )

    owner = seller or (existing.seller if existing else None) or _find_seller_for_original(
        original_transaction_id
    )
    if owner is None:
        raise AppleIapError(
            'No seller is linked to this App Store transaction yet.',
            code='seller_not_linked',
        )

    kind = mapped['kind']
    plan_slug = mapped.get('plan_slug') or ''
    billing_cycle = mapped.get('billing_cycle') or ''
    sms_quantity = 0
    excel_days = int(mapped.get('excel_duration_days') or 0)
    expires_at = None
    extra = {}

    if kind == SellerAppleIapTransaction.KIND_SUBSCRIPTION:
        plan = SubscriptionPlan.objects.filter(slug=plan_slug, is_active=True).first()
        if plan is None:
            raise AppleIapError('Subscription plan not found.', code='invalid_plan')
        expires_at = _period_end_for(payload, billing_cycle)
        amount = (
            Decimal(str(plan.price_yearly))
            if billing_cycle == 'yearly'
            else Decimal(str(plan.price_monthly))
        )
        activate_paid_subscription(
            seller=owner,
            plan=plan,
            billing_cycle=billing_cycle,
            billing_amount=amount,
            period_end=expires_at,
        )
        extra = {
            'message': 'Subscription activated',
            'plan_slug': plan.slug,
            'billing_cycle': billing_cycle,
        }
    elif kind == SellerAppleIapTransaction.KIND_SMS:
        pack = SmsPack.objects.filter(slug=plan_slug, is_active=True).first()
        if pack is None:
            raise AppleIapError('SMS pack not found.', code='invalid_pack')
        sms_quantity = int(pack.sms_quantity)
        new_balance = credit_sms_pack_balance(owner, sms_quantity)
        extra = {
            'message': 'SMS pack purchased',
            'pack_slug': pack.slug,
            'sms_quantity_added': sms_quantity,
            'sms_pack_balance': new_balance,
        }
    elif kind == SellerAppleIapTransaction.KIND_EXCEL:
        expires_at = extend_excel_report_addon(owner, excel_days)
        extra = {
            'message': 'Excel report addon activated',
            'plan_slug': plan_slug,
        }
    else:
        raise AppleIapError('Unknown App Store product.', code='unknown_product')

    defaults = {
        'seller': owner,
        'original_transaction_id': original_transaction_id,
        'product_id': product_id,
        'bundle_id': payload.get('bundleId') or payload.get('bundle_id') or '',
        'environment': payload.get('environment') or '',
        'kind': kind,
        'plan_slug': plan_slug,
        'billing_cycle': billing_cycle,
        'sms_quantity': sms_quantity,
        'excel_duration_days': excel_days,
        'status': SellerAppleIapTransaction.STATUS_GRANTED,
        'expires_at': expires_at,
        'notification_uuid': notification_uuid or '',
        'raw_payload': payload,
    }
    if existing:
        for key, value in defaults.items():
            setattr(existing, key, value)
        existing.save()
    else:
        SellerAppleIapTransaction.objects.create(transaction_id=transaction_id, **defaults)

    return _payload_result(seller=owner, kind=kind, extra=extra)


@transaction.atomic
def revoke_verified_transaction(*, payload: dict, notification_uuid: str = ''):
    product_id = str(payload.get('productId') or payload.get('product_id') or '')
    transaction_id = str(payload.get('transactionId') or payload.get('transaction_id') or '')
    original_transaction_id = str(
        payload.get('originalTransactionId')
        or payload.get('original_transaction_id')
        or transaction_id
    )
    seller = _find_seller_for_original(original_transaction_id)
    if seller is None:
        logger.info('Apple revoke for unknown originalTransactionId=%s', original_transaction_id)
        return {'ok': True, 'ignored': True}

    mapped = parse_product_id(product_id) if product_id else {'kind': SellerAppleIapTransaction.KIND_UNKNOWN}
    kind = mapped.get('kind')
    if kind == SellerAppleIapTransaction.KIND_SUBSCRIPTION:
        expire_seller_subscriptions(seller)
    elif kind == SellerAppleIapTransaction.KIND_EXCEL:
        settings_row, _ = SellerSettings.objects.select_for_update().get_or_create(seller=seller)
        settings_row.excel_report_addon_expires_at = timezone.now()
        settings_row.save(update_fields=['excel_report_addon_expires_at'])
    # Consumable SMS credits are not clawed back.

    SellerAppleIapTransaction.objects.filter(
        original_transaction_id=original_transaction_id
    ).update(status=SellerAppleIapTransaction.STATUS_REVOKED)

    if transaction_id:
        SellerAppleIapTransaction.objects.update_or_create(
            transaction_id=transaction_id,
            defaults={
                'seller': seller,
                'original_transaction_id': original_transaction_id,
                'product_id': product_id,
                'kind': kind or SellerAppleIapTransaction.KIND_UNKNOWN,
                'status': SellerAppleIapTransaction.STATUS_REVOKED,
                'notification_uuid': notification_uuid or '',
                'raw_payload': payload,
            },
        )
    return {'ok': True, 'revoked': True, 'kind': kind}


def verify_and_grant(*, seller, platform: str, product_id: str, transaction_id: str, signed_transaction: str):
    if (platform or 'ios').lower() not in ('ios', 'apple', 'appstore'):
        raise AppleIapError('Only iOS App Store purchases are supported.', code='unsupported_platform')
    payload = verify_signed_transaction(signed_transaction, transaction_id)
    signed_product = str(payload.get('productId') or payload.get('product_id') or '')
    if product_id and signed_product and product_id != signed_product:
        raise AppleIapError(
            'product_id does not match the signed transaction.',
            code='product_mismatch',
        )
    return grant_verified_transaction(seller=seller, payload=payload)


def handle_app_store_notification(signed_payload: str):
    raw = (signed_payload or '').strip()
    if not raw:
        raise AppleIapError('Missing signedPayload.', code='missing_payload')
    try:
        notification = verify_jws(raw)
    except AppleJwsError as exc:
        unverified = decode_jws_unverified(raw)
        if _allow_unverified_xcode(unverified):
            notification = unverified
        else:
            raise AppleIapError(exc.message, code=exc.code) from exc

    ntype = str(notification.get('notificationType') or '')
    uuid_value = str(notification.get('notificationUUID') or '')
    if uuid_value and SellerAppleIapTransaction.objects.filter(notification_uuid=uuid_value).exists():
        return {'ok': True, 'idempotent': True}

    data = notification.get('data') or {}
    signed_tx = data.get('signedTransactionInfo') or ''
    payload = verify_jws(signed_tx) if signed_tx else {}

    if ntype in REVOKE_TYPES:
        return revoke_verified_transaction(payload=payload, notification_uuid=uuid_value)
    if ntype in RENEW_TYPES or ntype in ('DID_CHANGE_RENEWAL_PREF', 'DID_FAIL_TO_RENEW', 'TEST'):
        if ntype in ('DID_CHANGE_RENEWAL_PREF', 'DID_FAIL_TO_RENEW', 'TEST') and not signed_tx:
            return {'ok': True, 'ignored': True, 'notificationType': ntype}
        if not payload:
            return {'ok': True, 'ignored': True, 'notificationType': ntype}
        seller = _find_seller_for_original(
            str(payload.get('originalTransactionId') or payload.get('transactionId') or '')
        )
        return grant_verified_transaction(
            seller=seller,
            payload=payload,
            notification_uuid=uuid_value,
        )
    logger.info('Unhandled Apple IAP notificationType=%s', ntype)
    return {'ok': True, 'ignored': True, 'notificationType': ntype}
