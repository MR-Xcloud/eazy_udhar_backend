from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

INVOICE_DOWNLOAD_SALT = 'invoice-download'
INVOICE_DOWNLOAD_MAX_AGE = 60 * 60  # 1 hour


def make_invoice_download_token(invoice_id) -> str:
    return TimestampSigner(salt=INVOICE_DOWNLOAD_SALT).sign(str(invoice_id))


def verify_invoice_download_token(token: str, invoice_id) -> bool:
    if not token:
        return False
    try:
        value = TimestampSigner(salt=INVOICE_DOWNLOAD_SALT).unsign(
            token, max_age=INVOICE_DOWNLOAD_MAX_AGE
        )
    except (BadSignature, SignatureExpired):
        return False
    return value == str(invoice_id)
