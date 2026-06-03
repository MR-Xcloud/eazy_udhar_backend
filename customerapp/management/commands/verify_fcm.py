import json
from pathlib import Path

from django.core.management.base import BaseCommand

from easyudhar.fcm import (
    fcm_enabled,
    resolve_firebase_credentials_path,
    resolve_firebase_project_id,
    _ensure_firebase_app,
)
from customerapp.models import CustomerDeviceToken
from sellerapp.models import SellerDeviceToken


class Command(BaseCommand):
    help = 'Verify Firebase credentials and optionally send a test push.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--token',
            help='Send a one-off test push to this FCM registration token.',
        )

    def handle(self, *args, **options):
        project_id = resolve_firebase_project_id()
        cred_path = resolve_firebase_credentials_path()

        self.stdout.write(f'Project ID: {project_id or "(not set)"}')
        self.stdout.write(f'Credentials: {cred_path or "(not set)"}')

        if cred_path:
            path = Path(cred_path)
            if not path.exists():
                self.stderr.write(self.style.ERROR(f'Credentials file not found: {path}'))
                return
            try:
                with open(path, encoding='utf-8') as handle:
                    data = json.load(handle)
                self.stdout.write(
                    f'Service account: {data.get("client_email", "?")}'
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.stderr.write(self.style.ERROR(f'Invalid JSON: {exc}'))
                return

        if not fcm_enabled():
            self.stderr.write(
                self.style.ERROR(
                    'FCM not enabled. Place service-account.json at '
                    'easyudhar/firebase/service-account.json or set env vars.'
                )
            )
            return

        app = _ensure_firebase_app()
        if app is None:
            self.stderr.write(self.style.ERROR('Firebase Admin SDK failed to initialize.'))
            return

        self.stdout.write(self.style.SUCCESS('Firebase Admin SDK initialized OK.'))

        customer_tokens = CustomerDeviceToken.objects.filter(is_active=True).count()
        seller_tokens = SellerDeviceToken.objects.filter(is_active=True).count()
        self.stdout.write(f'Active customer device tokens: {customer_tokens}')
        self.stdout.write(f'Active seller device tokens: {seller_tokens}')

        test_token = options.get('token')
        if not test_token:
            if customer_tokens == 0 and seller_tokens == 0:
                self.stdout.write(
                    self.style.WARNING(
                        'No device tokens in DB yet. Log in on the app after Firebase '
                        'is configured, then check admin -> device tokens.'
                    )
                )
            return

        sent = _send_direct_test(test_token)
        if sent:
            self.stdout.write(self.style.SUCCESS(f'Test push sent to {test_token[:20]}...'))
        else:
            self.stderr.write(self.style.ERROR('Test push failed (check token and logs).'))


def _send_direct_test(token):
    from firebase_admin import messaging

    from easyudhar.fcm import _ensure_firebase_app

    if _ensure_firebase_app() is None:
        return False
    try:
        messaging.send(
            messaging.Message(
                notification=messaging.Notification(
                    title='EasyUdhar test push',
                    body='FCM is working from the backend.',
                ),
                data={
                    'type': 'general',
                    'notification_id': 'test',
                    'reference_id': 'verify_fcm',
                },
                token=token,
            )
        )
        return True
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception('Test FCM send failed: %s', exc)
        return False
