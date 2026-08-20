"""Postmark outbound activity for one recipient.

Postmark keeps the delivery/open/click story, not us — so instead of mirroring
it into a local table we read it live per recipient. The list endpoint only
knows "Sent", so the per-message *details* call is what turns a row into a
timeline (Delivered / Opened / LinkClicked / Bounced). Those are fetched in a
small thread pool and cached briefly, because one recipient page is ~25 HTTP
round-trips and admins reopen the same dialog repeatedly.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.cache import cache

API_BASE = 'https://api.postmarkapp.com'
CACHE_TTL = 120
DETAIL_WORKERS = 6
TIMEOUT = 20


class PostmarkError(Exception):
    pass


def configured():
    return bool((getattr(settings, 'POSTMARK_SERVER_TOKEN', '') or '').strip())


def _get(path, params=None):
    url = f'{API_BASE}{path}'
    if params:
        url = f'{url}?{urllib.parse.urlencode(params)}'
    req = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/json',
            'X-Postmark-Server-Token': settings.POSTMARK_SERVER_TOKEN,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors='replace')[:300]
        raise PostmarkError(f'Postmark returned {exc.code}: {body}') from exc
    except Exception as exc:  # network / timeout / bad JSON
        raise PostmarkError(f'Could not reach Postmark: {exc}') from exc


def _first(events, *types):
    for ev in events:
        if ev.get('Type') in types:
            return ev
    return None


def _summarise(message, events):
    """Fold a message's event list into the columns the dialog shows."""
    events = sorted(events, key=lambda e: e.get('ReceivedAt') or '')
    opens = [e for e in events if e.get('Type') == 'Opened']
    clicks = [e for e in events if e.get('Type') == 'LinkClicked']
    delivered = _first(events, 'Delivered')
    bounced = _first(events, 'Bounced')
    transient = _first(events, 'Transient')

    if bounced:
        state = 'bounced'
    elif clicks:
        state = 'clicked'
    elif opens:
        state = 'opened'
    elif delivered:
        state = 'delivered'
    elif transient:
        state = 'deferred'
    else:
        state = 'sent'

    bounce_detail = None
    if bounced:
        details = bounced.get('Details') or {}
        bounce_detail = details.get('Summary') or details.get('BounceID') or None
    elif transient:
        bounce_detail = (transient.get('Details') or {}).get('DeliveryMessage')

    first_click = clicks[0] if clicks else None
    return {
        'message_id': message.get('MessageID'),
        'subject': message.get('Subject') or '(no subject)',
        'to': ', '.join(message.get('Recipients') or []) or message.get('To') or '',
        'from_email': message.get('From') or '',
        'stream': message.get('MessageStream') or '',
        'sent_at': message.get('ReceivedAt'),
        'state': state,
        'delivered_at': delivered.get('ReceivedAt') if delivered else None,
        'first_opened_at': opens[0].get('ReceivedAt') if opens else None,
        'open_count': len(opens),
        'first_clicked_at': first_click.get('ReceivedAt') if first_click else None,
        'click_count': len(clicks),
        'clicked_url': (first_click.get('Details') or {}).get('Link') if first_click else None,
        'bounced_at': bounced.get('ReceivedAt') if bounced else None,
        'bounce_detail': bounce_detail,
        'events': [
            {
                'type': e.get('Type'),
                'at': e.get('ReceivedAt'),
                'detail': _event_detail(e),
            }
            for e in events
        ],
    }


def _event_detail(event):
    details = event.get('Details') or {}
    if event.get('Type') == 'LinkClicked':
        return details.get('Link')
    if event.get('Type') == 'Opened':
        client = (event.get('Client') or {}).get('Name')
        os_name = (event.get('OS') or {}).get('Name')
        return ' · '.join(x for x in (client, os_name) if x) or None
    if event.get('Type') in ('Bounced', 'Transient'):
        return details.get('Summary') or details.get('DeliveryMessage')
    if event.get('Type') == 'Delivered':
        return details.get('DeliveryMessage')
    return None


def _details(message_id):
    try:
        return _get(f'/messages/outbound/{message_id}/details').get('MessageEvents') or []
    except PostmarkError:
        # One unreadable message must not blank the whole timeline.
        return []


def activity_for(email, *, count=25, offset=0):
    """Recent outbound Postmark messages to `email`, each with its events."""
    email = (email or '').strip().lower()
    if not email:
        raise PostmarkError('An email address is required.')
    if not configured():
        raise PostmarkError('Postmark is not configured (POSTMARK_SERVER_TOKEN).')

    count = max(1, min(int(count or 25), 100))
    offset = max(0, int(offset or 0))
    cache_key = f'postmark:activity:{email}:{count}:{offset}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    listing = _get(
        '/messages/outbound',
        {'recipient': email, 'count': count, 'offset': offset},
    )
    messages = listing.get('Messages') or []

    if messages:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
            event_lists = list(pool.map(lambda m: _details(m.get('MessageID')), messages))
    else:
        event_lists = []

    rows = [_summarise(m, ev) for m, ev in zip(messages, event_lists)]
    result = {
        'email': email,
        'total': listing.get('TotalCount', len(rows)),
        'count': count,
        'offset': offset,
        'counts': {
            'sent': len(rows),
            'delivered': sum(1 for r in rows if r['delivered_at']),
            'opened': sum(1 for r in rows if r['open_count']),
            'clicked': sum(1 for r in rows if r['click_count']),
            'bounced': sum(1 for r in rows if r['bounced_at']),
        },
        'messages': rows,
    }
    cache.set(cache_key, result, CACHE_TTL)
    return result
