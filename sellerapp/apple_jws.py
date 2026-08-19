"""Verify App Store Server JWS (StoreKit 2 signed transactions / notifications)."""

from __future__ import annotations

import base64
import json
import logging
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

APPLE_ROOT_CA_G3_URL = 'https://www.apple.com/certificateauthority/AppleRootCA-G3.cer'
APPLE_TRANSACTION_OID = '1.2.840.113635.100.6.11.1'


class AppleJwsError(Exception):
    def __init__(self, message, *, code='invalid_jws'):
        super().__init__(message)
        self.message = message
        self.code = code


def _b64url_decode(part: str) -> bytes:
    padded = part + '=' * ((4 - len(part) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode('ascii'))


def decode_jws_unverified(token: str) -> dict:
    parts = (token or '').strip().split('.')
    if len(parts) != 3:
        raise AppleJwsError('Not a JWS compact serialization.', code='invalid_jws')
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppleJwsError('JWS payload is not JSON.', code='invalid_jws') from exc
    if not isinstance(payload, dict):
        raise AppleJwsError('JWS payload must be an object.', code='invalid_jws')
    return payload


def _load_der_or_pem(data: bytes):
    from cryptography import x509

    try:
        return x509.load_der_x509_certificate(data)
    except ValueError:
        return x509.load_pem_x509_certificate(data)


@lru_cache(maxsize=1)
def _apple_root_cert():
    configured = (getattr(settings, 'APPLE_IAP_ROOT_CA_PATH', '') or '').strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    base = Path(__file__).resolve().parent / 'certs'
    candidates.append(base / 'AppleRootCA-G3.pem')
    candidates.append(base / 'AppleRootCA-G3.cer')

    for path in candidates:
        if path.is_file():
            return _load_der_or_pem(path.read_bytes())

    try:
        with urlopen(APPLE_ROOT_CA_G3_URL, timeout=15) as response:
            data = response.read()
        cert = _load_der_or_pem(data)
    except Exception as exc:
        raise AppleJwsError(
            'Could not load Apple Root CA G3 to verify the purchase.',
            code='apple_root_ca_missing',
        ) from exc

    try:
        base.mkdir(parents=True, exist_ok=True)
        (base / 'AppleRootCA-G3.cer').write_bytes(data)
    except OSError:
        logger.warning('Could not cache Apple Root CA G3 locally')
    return cert


def _p1363_to_der(signature: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    if len(signature) % 2:
        raise AppleJwsError('Invalid ECDSA signature length.', code='invalid_jws')
    half = len(signature) // 2
    r = int.from_bytes(signature[:half], 'big')
    s = int.from_bytes(signature[half:], 'big')
    return encode_dss_signature(r, s)


def _verify_cert_signature(cert, issuer) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    key = issuer.public_key()
    try:
        if isinstance(key, rsa.RSAPublicKey):
            key.verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )
        else:
            key.verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                ec.ECDSA(cert.signature_hash_algorithm),
            )
    except InvalidSignature as exc:
        raise AppleJwsError(
            'App Store certificate chain is invalid.',
            code='invalid_jws',
        ) from exc


def _verify_chain(certs) -> None:
    from datetime import datetime, timezone

    if not certs:
        raise AppleJwsError('JWS is missing the x5c certificate chain.', code='invalid_jws')

    now = datetime.now(timezone.utc)
    for cert in certs:
        start = getattr(cert, 'not_valid_before_utc', None)
        end = getattr(cert, 'not_valid_after_utc', None)
        if start is None:
            start = cert.not_valid_before.replace(tzinfo=timezone.utc)
        if end is None:
            end = cert.not_valid_after.replace(tzinfo=timezone.utc)
        if start > now or end < now:
            raise AppleJwsError('App Store signing certificate is expired.', code='invalid_jws')

    root = _apple_root_cert()
    chain = list(certs) + [root]
    for index, cert in enumerate(chain[:-1]):
        _verify_cert_signature(cert, chain[index + 1])


def verify_jws(token: str, *, require_transaction_oid: bool = False) -> dict:
    """Verify ES256 JWS with Apple's x5c chain rooted at Apple Root CA G3."""
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.hashes import SHA256

    parts = (token or '').strip().split('.')
    if len(parts) != 3:
        raise AppleJwsError('Not a JWS compact serialization.', code='invalid_jws')

    try:
        header = json.loads(_b64url_decode(parts[0]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppleJwsError('JWS header is not JSON.', code='invalid_jws') from exc

    x5c = header.get('x5c') or []
    if not x5c:
        raise AppleJwsError('JWS is missing x5c certificates.', code='invalid_jws')

    certs = []
    for entry in x5c:
        try:
            der = base64.b64decode(entry)
            certs.append(x509.load_der_x509_certificate(der))
        except Exception as exc:
            raise AppleJwsError('JWS x5c certificate is invalid.', code='invalid_jws') from exc

    _verify_chain(certs)

    if require_transaction_oid:
        oids = [
            ext.oid.dotted_string
            for ext in certs[0].extensions
        ]
        if APPLE_TRANSACTION_OID not in oids:
            logger.info('Apple transaction OID not present on leaf certificate')

    signing_input = f'{parts[0]}.{parts[1]}'.encode('ascii')
    signature = _p1363_to_der(_b64url_decode(parts[2]))
    try:
        certs[0].public_key().verify(signature, signing_input, ec.ECDSA(SHA256()))
    except InvalidSignature as exc:
        raise AppleJwsError('App Store JWS signature is invalid.', code='invalid_jws') from exc

    return decode_jws_unverified(token)
