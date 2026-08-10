"""Signed Telegram deep-link payloads — proves a /start came from a link we generated
for a specific seller, without needing a lookup table keyed by guessable seller ids.
"""

import hashlib
import hmac

from django.conf import settings


def _mac(seller_id):
    return hmac.new(
        settings.SECRET_KEY.encode(),
        str(seller_id).encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


def make_start_payload(seller_id):
    """Telegram restricts start payloads to [A-Za-z0-9_-]{1,64} — keep it alnum + underscore."""
    return f's{seller_id}_{_mac(seller_id)}'


def verify_start_payload(payload):
    """Returns the seller_id if the payload is genuine, else None."""
    if not payload or not payload.startswith('s') or '_' not in payload:
        return None
    seller_id_str, _, mac = payload[1:].rpartition('_')
    if not seller_id_str.isdigit():
        return None
    seller_id = int(seller_id_str)
    if not hmac.compare_digest(mac, _mac(seller_id)):
        return None
    return seller_id
