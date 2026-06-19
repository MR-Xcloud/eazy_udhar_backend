"""Shared payment method normalization for seller + customer apps."""

PAYMENT_METHOD_CASH = 'cash'
PAYMENT_METHOD_UPI = 'upi'
PAYMENT_METHOD_BANK = 'bank'
PAYMENT_METHOD_CARD = 'card'
PAYMENT_METHOD_CHEQUE = 'cheque'
PAYMENT_METHOD_WALLET = 'wallet'
PAYMENT_METHOD_OTHER = 'other'

PAYMENT_METHOD_CHOICES = [
    (PAYMENT_METHOD_CASH, 'Cash'),
    (PAYMENT_METHOD_UPI, 'UPI'),
    (PAYMENT_METHOD_BANK, 'Bank Transfer'),
    (PAYMENT_METHOD_CARD, 'Card'),
    (PAYMENT_METHOD_CHEQUE, 'Cheque'),
    (PAYMENT_METHOD_WALLET, 'Wallet'),
]

SELLER_PAYMENT_METHODS = {
    PAYMENT_METHOD_CASH,
    PAYMENT_METHOD_UPI,
    PAYMENT_METHOD_BANK,
    PAYMENT_METHOD_CARD,
    PAYMENT_METHOD_CHEQUE,
    PAYMENT_METHOD_WALLET,
}

CUSTOMER_ONLINE_METHODS = {
    PAYMENT_METHOD_UPI,
    PAYMENT_METHOD_CARD,
    PAYMENT_METHOD_BANK,
    PAYMENT_METHOD_WALLET,
}

_METHOD_ALIASES = {
    'cash': PAYMENT_METHOD_CASH,
    'upi': PAYMENT_METHOD_UPI,
    'upi_id': PAYMENT_METHOD_UPI,
    'gpay': PAYMENT_METHOD_UPI,
    'phonepe': PAYMENT_METHOD_UPI,
    'paytm': PAYMENT_METHOD_UPI,
    'bank': PAYMENT_METHOD_BANK,
    'bank_transfer': PAYMENT_METHOD_BANK,
    'bank transfer': PAYMENT_METHOD_BANK,
    'netbanking': PAYMENT_METHOD_BANK,
    'neft': PAYMENT_METHOD_BANK,
    'rtgs': PAYMENT_METHOD_BANK,
    'imps': PAYMENT_METHOD_BANK,
    'card': PAYMENT_METHOD_CARD,
    'credit_card': PAYMENT_METHOD_CARD,
    'debit_card': PAYMENT_METHOD_CARD,
    'credit card': PAYMENT_METHOD_CARD,
    'debit card': PAYMENT_METHOD_CARD,
    'cheque': PAYMENT_METHOD_CHEQUE,
    'check': PAYMENT_METHOD_CHEQUE,
    'wallet': PAYMENT_METHOD_WALLET,
    'razorpay': PAYMENT_METHOD_UPI,
}

_RAZORPAY_METHOD_MAP = {
    'upi': PAYMENT_METHOD_UPI,
    'card': PAYMENT_METHOD_CARD,
    'credit': PAYMENT_METHOD_CARD,
    'debit': PAYMENT_METHOD_CARD,
    'netbanking': PAYMENT_METHOD_BANK,
    'bank_transfer': PAYMENT_METHOD_BANK,
    'wallet': PAYMENT_METHOD_WALLET,
    'emi': PAYMENT_METHOD_CARD,
}

_METHOD_LABELS = dict(PAYMENT_METHOD_CHOICES)
_METHOD_LABELS[PAYMENT_METHOD_OTHER] = 'Other'


def normalize_payment_method(value, *, default=PAYMENT_METHOD_OTHER):
    text = (value or '').strip().lower().replace('-', '_')
    if not text:
        return default
    if text in _METHOD_ALIASES:
        return _METHOD_ALIASES[text]
    if text in SELLER_PAYMENT_METHODS:
        return text
    return default


def normalize_seller_payment_method(value):
    method = normalize_payment_method(value, default=PAYMENT_METHOD_OTHER)
    if method not in SELLER_PAYMENT_METHODS:
        allowed = ', '.join(sorted(SELLER_PAYMENT_METHODS))
        raise ValueError(f'Invalid payment method. Allowed: {allowed}')
    return method


def razorpay_method_to_standard(razorpay_method):
    key = (razorpay_method or '').strip().lower()
    return _RAZORPAY_METHOD_MAP.get(key, PAYMENT_METHOD_UPI)


def payment_method_label(method):
    slug = normalize_payment_method(method)
    return _METHOD_LABELS.get(slug, slug.replace('_', ' ').title())


def payment_methods_catalog(*, online=False):
    """Return method list for mobile UI pickers."""
    methods = CUSTOMER_ONLINE_METHODS if online else SELLER_PAYMENT_METHODS
    return [
        {
            'id': method_id,
            'label': payment_method_label(method_id),
            'online': method_id in CUSTOMER_ONLINE_METHODS,
            'seller_manual': method_id in SELLER_PAYMENT_METHODS,
        }
        for method_id, _label in PAYMENT_METHOD_CHOICES
        if method_id in methods
    ]
