import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_firebase_app = None
_init_attempted = False


def _firebase_dir():
    return Path(__file__).resolve().parent.parent / 'firebase'


def resolve_firebase_credentials_path():
    env_path = os.getenv('FIREBASE_CREDENTIALS_PATH', '').strip()
    if env_path:
        return env_path

    firebase_dir = _firebase_dir()
    default_path = firebase_dir / 'service-account.json'
    if default_path.exists():
        return str(default_path)

    for candidate in sorted(firebase_dir.glob('*firebase-adminsdk*.json')):
        return str(candidate)
    return ''


def resolve_firebase_project_id():
    env_id = os.getenv('FIREBASE_PROJECT_ID', '').strip()
    if env_id:
        return env_id

    json_path = _firebase_dir() / 'google-services.json'
    if json_path.exists():
        try:
            with open(json_path, encoding='utf-8') as handle:
                return json.load(handle).get('project_id', '').strip()
        except (OSError, json.JSONDecodeError):
            logger.exception('Failed to read project_id from %s', json_path)

    cred_path = resolve_firebase_credentials_path()
    if cred_path:
        try:
            with open(cred_path, encoding='utf-8') as handle:
                return json.load(handle).get('project_id', '').strip()
        except (OSError, json.JSONDecodeError):
            logger.exception('Failed to read project_id from %s', cred_path)
    return ''


def use_application_default_credentials():
    """Use gcloud ADC when org policy blocks service-account key download."""
    value = os.getenv('FIREBASE_USE_ADC', '').strip().lower()
    if value in {'1', 'true', 'yes'}:
        return True
    if value in {'0', 'false', 'no'}:
        return False
    # No key file on disk — try ADC automatically (local gcloud login or GCP runtime).
    return not resolve_firebase_credentials_path()


def fcm_health_status():
    """Return (ok, message) for admin integration health."""
    if not fcm_enabled():
        return False, 'Required credentials not configured.'
    if _ensure_firebase_app() is None:
        return False, 'Credentials found but Firebase Admin SDK failed to initialize.'
    return True, ''


def fcm_enabled():
    project_id = resolve_firebase_project_id()
    if not project_id:
        return False
    return bool(resolve_firebase_credentials_path() or use_application_default_credentials())


def _ensure_firebase_app():
    global _firebase_app, _init_attempted
    if _firebase_app is not None:
        return _firebase_app
    if _init_attempted:
        return None

    _init_attempted = True
    if not fcm_enabled():
        logger.info(
            'FCM disabled — set FIREBASE_PROJECT_ID and credentials '
            '(service-account.json or FIREBASE_USE_ADC=true with gcloud login)'
        )
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        project_id = resolve_firebase_project_id()
        options = {'projectId': project_id}
        cred_path = resolve_firebase_credentials_path()
        if cred_path:
            cred = credentials.Certificate(cred_path)
        else:
            cred = credentials.ApplicationDefault()
        _firebase_app = firebase_admin.initialize_app(cred, options)
        return _firebase_app
    except Exception:
        logger.exception('Failed to initialize Firebase Admin SDK')
        return None


def _stringify_data(data):
    return {key: '' if value is None else str(value) for key, value in data.items()}


def _deactivate_tokens(model, tokens):
    if tokens:
        model.objects.filter(token__in=tokens).update(is_active=False)


def _send_to_tokens(token_model, owner_filter, *, title, body, data):
    app = _ensure_firebase_app()
    if app is None:
        return 0

    from firebase_admin import messaging

    tokens = list(
        token_model.objects.filter(is_active=True, **owner_filter).values_list('token', flat=True)
    )
    if not tokens:
        return 0

    payload = _stringify_data(data)
    messages = [
        messaging.Message(
            notification=messaging.Notification(title=title, body=body or title),
            data=payload,
            token=token,
        )
        for token in tokens
    ]

    invalid_tokens = []
    sent = 0
    try:
        batch = messaging.send_each(messages)
    except Exception:
        logger.exception('FCM send_each failed')
        return 0

    for idx, response in enumerate(batch.responses):
        if response.success:
            sent += 1
            continue
        error = response.exception
        if error and getattr(error, 'code', '') in {
            'NOT_FOUND',
            'UNREGISTERED',
            'INVALID_ARGUMENT',
        }:
            invalid_tokens.append(tokens[idx])
        else:
            logger.warning('FCM send failed for token index %s: %s', idx, error)

    _deactivate_tokens(token_model, invalid_tokens)
    return sent


def _customer_push_enabled(user_id):
    from customerapp.models import CustomerSettings

    settings = CustomerSettings.objects.filter(user_id=user_id).first()
    return settings is None or settings.push_notifications_enabled


def _seller_push_enabled(seller_id):
    from sellerapp.models import SellerSettings

    settings = SellerSettings.objects.filter(seller_id=seller_id).first()
    return settings is None or settings.push_notifications_enabled


def push_customer_notification(notification):
    from customerapp.models import CustomerDeviceToken

    if not _customer_push_enabled(notification.user_id):
        return 0

    shop_id = ''
    if notification.shop_account_id:
        shop_id = str(notification.shop_account_id)

    return _send_to_tokens(
        CustomerDeviceToken,
        {'user_id': notification.user_id},
        title=notification.title,
        body=notification.subtitle,
        data={
            'type': notification.notification_type,
            'notification_id': str(notification.id),
            'reference_id': notification.reference_id or '',
            'shop_id': shop_id,
        },
    )


def push_seller_notification(notification):
    from sellerapp.models import SellerDeviceToken

    if not _seller_push_enabled(notification.seller_id):
        return 0

    customer_id = ''
    if notification.seller_customer_id:
        customer_id = str(notification.seller_customer_id)

    return _send_to_tokens(
        SellerDeviceToken,
        {'seller_id': notification.seller_id},
        title=notification.title,
        body=notification.subtitle,
        data={
            'type': notification.notification_type,
            'notification_id': str(notification.id),
            'reference_id': notification.reference_id or '',
            'customer_id': customer_id,
        },
    )
