"""Record where an account signed up from.

Both ``sellerapp.Seller`` and ``customerapp.Customer`` carry the same
``signup_*`` columns, so one helper serves both.

The IP is stored synchronously — it costs nothing and it is the raw fact we can
always re-resolve later. The city lookup may hit the network, so it runs on a
background thread and never delays the registration response.
"""

import logging
import threading

from django.db import close_old_connections

from . import geoip

logger = logging.getLogger(__name__)

GEO_FIELDS = ('signup_city', 'signup_region', 'signup_country', 'signup_source', 'signup_located_at')


def capture_signup_location(user, request, background=True):
    """Stamp the signup IP now; resolve the city now or shortly after."""
    ip = geoip.client_ip(request)
    if not ip:
        return
    try:
        user.signup_ip = ip
        user.save(update_fields=['signup_ip'])
    except Exception as exc:
        logger.warning('Could not store signup IP for %s#%s: %s', type(user).__name__, user.pk, exc)
        return

    if background:
        thread = threading.Thread(
            target=_resolve_in_background,
            args=(type(user), user.pk, ip),
            daemon=True,
        )
        thread.start()
    else:
        resolve_for(user, ip)


def _resolve_in_background(model, pk, ip):
    close_old_connections()
    try:
        user = model.objects.filter(pk=pk).first()
        if user is not None:
            resolve_for(user, ip)
    except Exception as exc:
        logger.warning('Signup geo lookup failed for %s#%s: %s', model.__name__, pk, exc)
    finally:
        close_old_connections()


def resolve_for(user, ip=None):
    """Fill the city/region/country columns from an IP. Returns True if stored."""
    from django.utils import timezone

    ip = ip or user.signup_ip
    location = geoip.resolve(ip)
    if not location:
        return False

    user.signup_city = location['city']
    user.signup_region = location['region']
    user.signup_country = location['country']
    user.signup_source = location['source']
    user.signup_located_at = timezone.now()
    user.save(update_fields=list(GEO_FIELDS))
    return True
