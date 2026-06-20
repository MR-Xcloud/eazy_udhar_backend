"""Razorpay Route — route customer payments to each seller's linked bank account."""

from decimal import Decimal

from django.conf import settings

from customerapp.razorpay_service import RazorpayError, _amount_paise, _razorpay_request


def route_enabled():
    return getattr(settings, 'RAZORPAY_ROUTE_ENABLED', True)


def resolve_seller_for_account(account):
    if account is None:
        return None
    if account.seller_id:
        return account.seller
    sc = getattr(account, 'seller_customer', None)
    if sc is not None and sc.seller_id:
        return sc.seller
    return None


def seller_payout_ready(seller):
    if not route_enabled():
        return True
    if not seller:
        return False
    bank = (seller.bank_account_number or '').strip()
    ifsc = (seller.bank_ifsc or '').strip()
    name = (seller.bank_account_holder or seller.full_name or seller.business_name or '').strip()
    return bool(bank and ifsc and name)


def ensure_seller_linked_account(seller):
    """Create/update Razorpay Route linked account for a seller."""
    if not route_enabled():
        return None

    if not seller_payout_ready(seller):
        raise RazorpayError(
            'Seller must add bank account (account number, IFSC, holder name) '
            'before accepting online payments.',
            code='seller_payout_not_configured',
        )

    linked_id = (seller.razorpay_linked_account_id or '').strip()
    if linked_id:
        _upsert_seller_bank_account(seller, linked_id)
        return linked_id

    payload = {
        'email': seller.email,
        'phone': _normalize_phone(seller.phone),
        'type': 'route',
        'reference_id': f'eazyudhar_seller_{seller.id}',
        'legal_business_name': (seller.business_name or 'Shop')[:100],
        'business_type': 'proprietorship',
        'contact_name': (seller.full_name or seller.business_name or 'Seller')[:100],
        'profile': {
            'category': 'others',
            'subcategory': 'others',
            'addresses': {
                'registered': {
                    'street1': ((seller.address or '').strip() or 'India')[:100],
                    'city': 'NA',
                    'state': 'NA',
                    'postal_code': '110001',
                    'country': 'IN',
                }
            },
        },
    }
    account = _razorpay_request('POST', '/accounts', payload)
    linked_id = account.get('id')
    if not linked_id:
        raise RazorpayError(
            'Could not create Razorpay linked account for seller.',
            code='route_account_failed',
        )

    seller.razorpay_linked_account_id = linked_id
    seller.razorpay_route_status = account.get('status') or 'created'
    seller.save(update_fields=['razorpay_linked_account_id', 'razorpay_route_status', 'updated_at'])

    _upsert_seller_bank_account(seller, linked_id)
    _request_route_product(linked_id)
    return linked_id


def _normalize_phone(phone):
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    if len(digits) == 10:
        return digits
    if len(digits) > 10:
        return digits[-10:]
    return '9999999999'


def _upsert_seller_bank_account(seller, linked_id):
    payload = {
        'ifsc_code': (seller.bank_ifsc or '').strip().upper(),
        'account_number': (seller.bank_account_number or '').strip(),
        'beneficiary_name': (
            seller.bank_account_holder
            or seller.full_name
            or seller.business_name
            or 'Seller'
        )[:120],
    }
    _razorpay_request('POST', f'/accounts/{linked_id}/bank_account', payload)


def _request_route_product(linked_id):
    try:
        _razorpay_request(
            'POST',
            f'/accounts/{linked_id}/products',
            {'product_name': 'route', 'tnc_accepted': True},
        )
    except RazorpayError:
        # Product may already exist or activation is async in Razorpay dashboard.
        pass


def plan_seller_amounts(targets, pay_amount, account=None):
    """Mirror customer payment allocation — amount per seller."""
    remaining = Decimal(str(pay_amount))
    by_seller = {}

    for acc in targets:
        if remaining <= 0:
            break
        outstanding = acc.outstanding_amount or Decimal('0')
        portion = min(remaining, outstanding)
        if portion <= 0:
            continue
        seller = resolve_seller_for_account(acc)
        if seller is None:
            raise RazorpayError(
                'Shop is not linked to a seller payout account.',
                code='seller_payout_not_configured',
            )
        by_seller[seller.id] = by_seller.get(seller.id, Decimal('0')) + portion
        remaining -= portion

    if remaining > 0 and account is not None and len(targets) == 1:
        seller = resolve_seller_for_account(targets[0])
        if seller is None:
            raise RazorpayError(
                'Shop is not linked to a seller payout account.',
                code='seller_payout_not_configured',
            )
        by_seller[seller.id] = by_seller.get(seller.id, Decimal('0')) + remaining

    if not by_seller:
        raise RazorpayError(
            'No seller payout destination for this payment.',
            code='seller_payout_not_configured',
        )
    return by_seller


def build_transfers_for_sellers(by_seller_amounts):
    """
    Build Razorpay Route transfers (100% to sellers — nothing retained on platform).
    by_seller_amounts: {seller_id: Decimal amount}
    """
    if not route_enabled():
        return []

    from sellerapp.models import Seller

    transfers = []
    for seller_id, amount in by_seller_amounts.items():
        seller = Seller.objects.filter(id=seller_id).first()
        if seller is None:
            raise RazorpayError('Seller not found for payout.', code='seller_not_found')
        linked_id = ensure_seller_linked_account(seller)
        paise = _amount_paise(amount)
        if paise <= 0:
            continue
        transfers.append(
            {
                'account': linked_id,
                'amount': paise,
                'currency': 'INR',
                'on_hold': False,
                'notes': {
                    'seller_id': str(seller.id),
                    'business_name': seller.business_name,
                },
            }
        )

    if not transfers:
        raise RazorpayError(
            'Could not build seller payout transfers.',
            code='seller_payout_not_configured',
        )

    total = sum(t['amount'] for t in transfers)
    return transfers, total


def transfers_for_single_seller(seller, amount, *, percentage=False):
    """Build Route transfer(s) for one seller (100% of payment to seller bank)."""
    if not route_enabled():
        return [], _amount_paise(amount)

    linked_id = ensure_seller_linked_account(seller)
    if percentage:
        transfers = [
            {
                'account': linked_id,
                'amount': 100,
                'currency': 'INR',
                'type': 'percentage',
                'on_hold': False,
                'notes': {
                    'seller_id': str(seller.id),
                    'business_name': seller.business_name,
                },
            }
        ]
        return transfers, _amount_paise(amount)

    by_seller = {seller.id: Decimal(str(amount))}
    return build_transfers_for_sellers(by_seller)


def attach_transfers_to_order_payload(payload, transfers):
    if transfers:
        payload['transfers'] = transfers
    return payload


def attach_transfers_to_payment_link_payload(payload, transfers):
    if transfers:
        payload['transfers'] = transfers
    return payload
