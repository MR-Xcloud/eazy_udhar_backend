"""Seller Contact Us / FAQ + Telegram support deep-link."""

import os

from django.conf import settings
from rest_framework.response import Response

from .seller_views import SellerAPIView


SELLER_FAQ = [
    {
        'question': 'How do I add a customer?',
        'answer': (
            'Tap the + button, choose Add customer (or save a transaction for a new phone '
            'number). Enter name and mobile — the customer is saved to your list.'
        ),
    },
    {
        'question': 'How do Credit and Receive work?',
        'answer': (
            'Credit adds udhar (purchase amount the customer owes). Receive records a '
            'payment against their balance. Extra payments can go to advance/wallet.'
        ),
    },
    {
        'question': 'How do payment reminders work?',
        'answer': (
            'You can send manual reminders from a customer page (SMS / WhatsApp / push). '
            'Automatic reminders can be turned on under Settings → Notifications & reminders.'
        ),
    },
    {
        'question': 'What counts toward my message quota?',
        'answer': (
            'Successful SMS and WhatsApp reminders, plus chat messages you send to '
            'customers, count against your plan message limit for the billing period.'
        ),
    },
    {
        'question': 'How do I set my UPI ID / QR?',
        'answer': (
            'Go to Settings → UPI ID, enter your UPI (e.g. name@upi), then save. '
            'Customers can pay using your QR from My QR code.'
        ),
    },
    {
        'question': 'How do subscriptions and SMS packs work?',
        'answer': (
            'Your plan includes a monthly message limit. When plan messages are used up, '
            'buy an SMS pack under Settings to keep sending SMS reminders.'
        ),
    },
    {
        'question': 'I see “token not valid” or get logged out',
        'answer': (
            'Your login session expired. Log in again. Keep the app updated — recent '
            'versions refresh the session automatically when possible.'
        ),
    },
    {
        'question': 'How do I contact EazyUdhar support?',
        'answer': (
            'Use Chat on Telegram below for the fastest help, or email support@eazyudhar.com.'
        ),
    },
]


def _telegram_payload():
    # Prefer live env so .env updates apply after process restart / reload.
    raw = (
        os.environ.get('TELEGRAM_BOT_USERNAME')
        or getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
        or ''
    ).strip()
    username = raw.lstrip('@')
    token = (
        os.environ.get('TELEGRAM_BOT_TOKEN')
        or getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        or ''
    ).strip()
    chat_url = f'https://t.me/{username}' if username else ''
    return {
        'enabled': bool(username),
        'username': username,
        'chat_url': chat_url,
        'bot_configured': bool(token),
    }


class SellerContactUsView(SellerAPIView):
    """GET seller/contact-us — FAQ + Telegram chat link (token never exposed)."""

    def get(self, request):
        return Response(
            {
                'title': 'Contact us',
                'support_email': (
                    os.environ.get('SUPPORT_EMAIL')
                    or getattr(settings, 'SUPPORT_EMAIL', '')
                    or 'support@eazyudhar.com'
                ),
                'faq': SELLER_FAQ,
                'telegram': _telegram_payload(),
            }
        )
