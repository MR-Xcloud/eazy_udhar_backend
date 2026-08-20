"""Resolve a client IP into a coarse (city, region, country) location.

Used to record where a seller / customer signed up from. Two providers, tried
in order:

  1. A local MaxMind GeoLite2-City database (``GEOIP_CITY_DB``). Offline, no
     rate limit — the preferred setup.
  2. MaxMind's GeoLite2 web service (``MAXMIND_ACCOUNT_ID`` /
     ``MAXMIND_LICENSE_KEY``). Same data, over HTTPS, 1000 lookups/day free.
  3. An anonymous HTTP service (``GEOIP_HTTP_URL``, default ip-api.com). Last
     resort — plain HTTP and rate limited by source IP.

Every entry point is failure-tolerant: a lookup that errors or times out
returns ``None`` and the caller simply stores no location. Signup must never
break because a geo provider is down.
"""

import ipaddress
import logging
import threading

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24 * 30  # a month; IP→city rarely moves

_reader = None
_reader_lock = threading.Lock()


def client_ip(request):
    """The caller's IP, honouring the X-Forwarded-For nginx sets."""
    if request is None:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def is_public_ip(ip):
    """False for loopback/private/reserved addresses — nothing to geolocate."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def resolve(ip):
    """Return ``{'city', 'region', 'country', 'source'}`` or None."""
    if not getattr(settings, 'GEOIP_ENABLED', True):
        return None
    if not is_public_ip(ip):
        return None

    key = f'geoip:{ip}'
    hit = cache.get(key)
    if hit is not None:
        return hit or None  # empty dict is a cached miss

    result = _lookup_maxmind(ip) or _lookup_maxmind_ws(ip) or _lookup_http(ip)
    cache.set(key, result or {}, CACHE_TTL)
    return result


def _lookup_maxmind_ws(ip):
    """MaxMind's GeoLite2 web service — authenticated, HTTPS, same data as the
    database. Used when no local .mmdb is installed."""
    account = getattr(settings, 'MAXMIND_ACCOUNT_ID', '')
    key = getattr(settings, 'MAXMIND_LICENSE_KEY', '')
    if not (account and key):
        return None

    host = getattr(settings, 'MAXMIND_WS_HOST', 'geolite.info')
    try:
        response = requests.get(
            f'https://{host}/geoip/v2.1/city/{ip}',
            auth=(account, key),
            timeout=getattr(settings, 'GEOIP_HTTP_TIMEOUT', 3),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.info('MaxMind web service lookup failed for %s: %s', ip, exc)
        return None

    subdivisions = payload.get('subdivisions') or []
    return _clean(
        {
            'city': _en(payload.get('city')),
            # Last subdivision is the most specific (state > district).
            'region': _en(subdivisions[-1]) if subdivisions else '',
            # Anycast ranges often carry only a registered_country.
            'country': _en(payload.get('country')) or _en(payload.get('registered_country')),
            'source': 'maxmind-ws',
        }
    )


def _en(node):
    """Pull the English name out of a MaxMind record node."""
    if not node:
        return ''
    return (node.get('names') or {}).get('en') or ''


def _lookup_maxmind(ip):
    reader = _get_reader()
    if reader is None:
        return None
    try:
        response = reader.city(ip)
    except Exception:  # AddressNotFoundError and friends
        return None

    subdivision = response.subdivisions.most_specific
    return _clean(
        {
            'city': response.city.name,
            'region': subdivision.name,
            # Anycast ranges often carry only a registered_country.
            'country': response.country.name or response.registered_country.name,
            'source': 'maxmind',
        }
    )


def _get_reader():
    """Open the GeoLite2 database once, lazily."""
    global _reader
    if _reader is not None:
        return _reader or None  # False marks "unavailable, don't retry"

    with _reader_lock:
        if _reader is not None:
            return _reader or None
        path = getattr(settings, 'GEOIP_CITY_DB', '')
        if not path:
            _reader = False
            return None
        try:
            import geoip2.database

            _reader = geoip2.database.Reader(path)
        except Exception as exc:
            logger.warning('GeoIP database unavailable (%s): %s', path, exc)
            _reader = False
            return None
        return _reader


def _lookup_http(ip):
    url = getattr(settings, 'GEOIP_HTTP_URL', '')
    if not url:
        return None
    try:
        response = requests.get(
            url.format(ip=ip),
            timeout=getattr(settings, 'GEOIP_HTTP_TIMEOUT', 3),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.info('GeoIP HTTP lookup failed for %s: %s', ip, exc)
        return None

    if payload.get('status') == 'fail':
        return None

    # ip-api.com field names, with common aliases for drop-in alternatives.
    return _clean(
        {
            'city': payload.get('city'),
            'region': payload.get('regionName') or payload.get('region'),
            'country': payload.get('country') or payload.get('country_name'),
            'source': 'ip-api',
        }
    )


def _clean(data):
    result = {k: (v or '').strip() for k, v in data.items()}
    if not (result['city'] or result['region'] or result['country']):
        return None
    return result
