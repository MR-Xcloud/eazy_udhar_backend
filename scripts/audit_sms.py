"""One-off SMS audit — run: python manage.py shell < scripts/audit_sms.py"""
from decimal import Decimal

from django.conf import settings

from customerapp.messaging import normalize_phone
from sellerapp.daily_sms import statement_link
from sellerapp.nimbus_sms import (
    _apply_template,
    _format_amount,
    nimbus_sms_configured,
)

NIMBUS_APPROVED = {
    'CREDIT3': 'Credit of Rs. {#var#} added to your account by {#var#} Check Balance and Details on {#var#} - EAZYUDHAR by INWIZY',
    'PAYMENT3': 'Payment of Rs. {#var#} credited to your account by {#var#} Check Balance and Details on {#var#} - EAZYUDHAR by INWIZY',
    'BALANCE': 'Payment Reminder: Balance of Rs. {#var#} is pending with {#var#} . View details on: {#var#} - EAZYUDHAR by INWIZY',
}

print('=== CONFIG CHECK ===')
checks = {
    'NIMBUS_SMS_ENABLED': settings.NIMBUS_SMS_ENABLED,
    'configured()': nimbus_sms_configured(),
    'USER_ID': settings.NIMBUS_USER_ID,
    'AUTH_KEY set': bool(settings.NIMBUS_AUTH_KEY),
    'ENTITY_ID': settings.NIMBUS_DLT_ENTITY_ID,
    'SENDER_ID': settings.NIMBUS_SENDER_ID,
    'API_URL': settings.NIMBUS_API_URL,
    'CATEGORY': settings.NIMBUS_SMS_CATEGORY,
    'SUB_CATEGORY': settings.NIMBUS_SMS_SUB_CATEGORY,
    'CREDIT_TID': settings.NIMBUS_CREDIT_TEMPLATE_ID,
    'PAYMENT_TID': settings.NIMBUS_PAYMENT_TEMPLATE_ID,
    'REMINDER_TID': settings.NIMBUS_REMINDER_TEMPLATE_ID,
    'MOBILE_PREFIX': repr(settings.NIMBUS_MOBILE_PREFIX),
    'EXTRA_PARAMS': repr(settings.NIMBUS_SMS_EXTRA_PARAMS),
}
for key, value in checks.items():
    print(f'  {key}: {value}')

print()
print('=== TEMPLATE TEXT MATCH (backend vs Nimbus approved) ===')
pairs = [
    ('CREDIT', settings.NIMBUS_CREDIT_SMS_TEXT, NIMBUS_APPROVED['CREDIT3']),
    ('PAYMENT', settings.NIMBUS_PAYMENT_SMS_TEXT, NIMBUS_APPROVED['PAYMENT3']),
    ('REMINDER', settings.NIMBUS_REMINDER_SMS_TEXT, NIMBUS_APPROVED['BALANCE']),
]
for name, backend, approved in pairs:
    match = backend == approved
    print(f'  {name}: {"EXACT MATCH" if match else "MISMATCH"}')
    if not match:
        print(f'    backend : {backend!r}')
        print(f'    approved: {approved!r}')

print()
print('=== REMINDER MESSAGE BUILD (Annu case) ===')
amount = _format_amount(Decimal('2000'))
shop = 'maa bhagwati engineering'
link = statement_link('XdtCz9uwe1ZFyTfuzzMN0Q')
text = _apply_template(
    settings.NIMBUS_REMINDER_SMS_TEXT,
    [amount, shop, link],
    raw_var_indices={2},
)
expected = (
    'Payment Reminder: Balance of Rs. 2000 is pending with maa bhagwati engineering . '
    'View details on: https://eazy-udhar-backend.onrender.com/XdtCz9uwe1ZFyTfuzzMN0Q - EAZYUDHAR by INWIZY'
)
print(f'  var1 amount: {amount!r}')
print(f'  var2 shop: {shop!r} (len={len(shop)})')
print(f'  var3 link: {link!r} (len={len(link)})')
print(f'  built text matches terminal log: {text == expected}')
print(f'  remaining placeholders: {text.count("{#var#}")}')

print()
print('=== PHONE NORMALIZATION ===')
for raw in ['7818947710', '+91 7818947710', '917818947710']:
    normalized = normalize_phone(raw)
    print(f'  {raw!r} -> {normalized!r} valid={len(normalized) == 10}')

print()
print('=== API PARAMS (reminder) ===')
phone = normalize_phone('+91 7818947710')
params = {
    'user': settings.NIMBUS_USER_ID,
    'sender': settings.NIMBUS_SENDER_ID,
    'mobile': phone,
    'entityid': settings.NIMBUS_DLT_ENTITY_ID,
    'templateid': settings.NIMBUS_REMINDER_TEMPLATE_ID,
    'rpt': '1',
    'category': settings.NIMBUS_SMS_CATEGORY,
    'subcategory': settings.NIMBUS_SMS_SUB_CATEGORY,
    'sub_category': settings.NIMBUS_SMS_SUB_CATEGORY,
}
for key, value in params.items():
    print(f'  {key}: {value}')
print(f'  text length: {len(text)} chars')

print()
print('=== SMS FLOWS ===')
print('  Credit/payment instant SMS: queued for nightly digest (not sent immediately)')
print('  Reminder SMS: sent immediately via send_reminder_sms')
print('  Nightly digest: uses CREDIT/PAYMENT template with URL in var3')

print()
print('=== BACKEND VERDICT ===')
flags = []
if len(settings.NIMBUS_SENDER_ID) != 6:
    flags.append(f'Sender ID length is {len(settings.NIMBUS_SENDER_ID)} (expected 6)')
if settings.NIMBUS_SMS_SUB_CATEGORY == 'implicit':
    flags.append('sub_category=implicit — verify BALANCE is Implicit on operator DLT portal')
if len(link) > 90:
    flags.append(f'Statement URL is {len(link)} chars')
else:
    flags.append(f'Statement URL length OK ({len(link)} chars)')
if not nimbus_sms_configured():
    flags.append('Nimbus NOT fully configured')
else:
    flags.append('All required Nimbus settings present')
if text == expected:
    flags.append('Reminder message text matches failed delivery log exactly')
for item in flags:
    print(f'  - {item}')
