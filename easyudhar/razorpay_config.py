from django.conf import settings


def get_razorpay_credentials():
    """Return (key_id, key_secret, webhook_secret) for current RAZORPAY_MODE."""
    if settings.RAZORPAY_MODE == 'live':
        return (
            settings.RAZORPAY_LIVE_KEY_ID,
            settings.RAZORPAY_LIVE_KEY_SECRET,
            settings.RAZORPAY_LIVE_WEBHOOK_SECRET,
        )
    return (
        settings.RAZORPAY_TEST_KEY_ID,
        settings.RAZORPAY_TEST_KEY_SECRET,
        settings.RAZORPAY_TEST_WEBHOOK_SECRET,
    )
