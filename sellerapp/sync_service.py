import uuid
from decimal import Decimal, InvalidOperation

from easyudhar.payment_utils import normalize_payment_method
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from customerapp.messaging import (
    link_seller_customer,
    notify_customer_added_by_seller,
)

from .models import LedgerTransaction, SellerCustomer, SellerNotification
from .services import (
    add_credit,
    customer_detail,
    customer_list_item,
    deposit_advance,
    receive_payment,
    transaction_item,
    use_advance,
)
from .utils import normalize_client_id, normalize_phone, parse_client_uuid, seller_customer_phone_exists


class SyncError(Exception):
    def __init__(self, message, code='error', status_code=422):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def parse_since(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        raise SyncError('Invalid since timestamp.', code='validation', status_code=422)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def find_customer_by_client_id(seller, client_id):
    if not client_id:
        return None
    try:
        cid = parse_client_uuid(client_id)
    except ValueError:
        return None
    if not cid:
        return None
    return SellerCustomer.objects.filter(seller=seller, client_id=cid).first()


def find_customer_by_phone(seller, phone):
    norm = normalize_phone(phone)
    if not norm:
        return None
    for customer in SellerCustomer.objects.filter(seller=seller).iterator():
        if normalize_phone(customer.phone) == norm:
            return customer
    return None


def find_transaction_by_client_id(seller, client_id):
    if not client_id:
        return None
    try:
        cid = parse_client_uuid(client_id)
    except ValueError:
        return None
    if not cid:
        return None
    return (
        LedgerTransaction.objects.filter(seller=seller, client_id=cid)
        .select_related('customer')
        .first()
    )


def _parse_client_uuid(client_id):
    try:
        return parse_client_uuid(client_id, required=True)
    except ValueError as exc:
        raise SyncError(str(exc), code='validation', status_code=422) from exc


def _parse_device_created_at(value):
    if not value:
        return None
    dt = parse_datetime(str(value)) if not hasattr(value, 'isoformat') else value
    if dt is None:
        raise SyncError('device_created_at must be ISO datetime.', code='validation', status_code=422)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def resolve_customer(seller, payload, id_map):
    """Resolve customer from server id, client_id map, or customer_client_id."""
    if payload.get('customer_id'):
        ref = payload['customer_id']
        normalized = normalize_client_id(ref)
        if normalized in id_map:
            return SellerCustomer.objects.get(seller=seller, id=id_map[normalized])
        try:
            uid = parse_client_uuid(ref, required=True)
        except ValueError as exc:
            raise SyncError(str(exc), code='validation', status_code=422) from exc
        customer = SellerCustomer.objects.filter(seller=seller, id=uid).first()
        if customer:
            return customer
        customer = find_customer_by_client_id(seller, uid)
        if customer:
            return customer
        raise SyncError('Customer not found.', code='customer_not_found', status_code=404)

    customer_client_id = payload.get('customer_client_id')
    if customer_client_id:
        normalized_client = normalize_client_id(customer_client_id)
        if normalized_client in id_map:
            return SellerCustomer.objects.get(seller=seller, id=id_map[normalized_client])
        if str(customer_client_id) in id_map:
            return SellerCustomer.objects.get(seller=seller, id=id_map[str(customer_client_id)])
        customer = find_customer_by_client_id(seller, customer_client_id)
        if customer:
            return customer
        raise SyncError(
            'Customer not found for customer_client_id. Sync customer first.',
            code='customer_not_found',
            status_code=404,
        )

    raise SyncError('customer_id or customer_client_id is required.', code='validation', status_code=422)


def create_customer_idempotent(
    seller,
    *,
    client_id=None,
    device_created_at=None,
    name='',
    phone='',
    email='',
    address='',
    city='',
    state='',
    country='India',
    notify=True,
):
    client_uuid = _parse_client_uuid(client_id) if client_id else None
    device_at = _parse_device_created_at(device_created_at)

    if client_uuid:
        existing = find_customer_by_client_id(seller, client_uuid)
        if existing:
            return existing, True

    phone = (phone or '').strip()
    if not phone:
        raise SyncError('Phone number is required.', code='validation', status_code=422)

    by_phone = find_customer_by_phone(seller, phone)
    if by_phone:
        if client_uuid and not by_phone.client_id:
            by_phone.client_id = client_uuid
            by_phone.save(update_fields=['client_id', 'updated_at'])
        return by_phone, True

    if seller_customer_phone_exists(seller, phone):
        by_phone = find_customer_by_phone(seller, phone)
        return by_phone, True

    customer = SellerCustomer.objects.create(
        seller=seller,
        client_id=client_uuid,
        device_created_at=device_at,
        name=name.strip() or 'Customer',
        phone=phone,
        email=email or '',
        address=address or '',
        city=city or '',
        state=state or '',
        country=country or 'India',
    )
    if notify:
        link_seller_customer(customer)
        notify_customer_added_by_seller(customer, seller)
    return customer, False


def _attach_tx_meta(tx, *, client_id=None, device_created_at=None):
    if client_id and not tx.client_id:
        tx.client_id = _parse_client_uuid(client_id)
    if device_created_at and not tx.device_created_at:
        tx.device_created_at = _parse_device_created_at(device_created_at)
    if client_id or device_created_at:
        tx.save(update_fields=['client_id', 'device_created_at', 'updated_at'])


def apply_credit_idempotent(
    seller, customer, amount, *, client_id=None, device_created_at=None, note='', send_sms=None, due_date=None
):
    client_uuid = _parse_client_uuid(client_id) if client_id else None
    if client_uuid:
        existing = find_transaction_by_client_id(seller, client_uuid)
        if existing:
            return existing, True, None

    tx, sms = add_credit(
        seller,
        customer,
        amount,
        note=note,
        send_sms=send_sms,
        client_id=client_uuid,
        device_created_at=_parse_device_created_at(device_created_at),
        due_date=due_date,
    )
    return tx, False, sms


def apply_payment_idempotent(
    seller,
    customer,
    amount,
    *,
    client_id=None,
    device_created_at=None,
    payment_method='UPI',
    note='',
    send_sms=None,
):
    client_uuid = _parse_client_uuid(client_id) if client_id else None
    if client_uuid:
        existing = find_transaction_by_client_id(seller, client_uuid)
        if existing:
            return existing, True, None

    tx, sms = receive_payment(
        seller,
        customer,
        amount,
        payment_method=normalize_payment_method(payment_method, default='upi'),
        note=note,
        send_sms=send_sms,
        client_id=client_uuid,
        device_created_at=_parse_device_created_at(device_created_at),
    )
    return tx, False, sms


def apply_advance_deposit_idempotent(
    seller,
    customer,
    amount,
    *,
    client_id=None,
    device_created_at=None,
    payment_method='UPI',
    note='',
):
    client_uuid = _parse_client_uuid(client_id) if client_id else None
    if client_uuid:
        existing = find_transaction_by_client_id(seller, client_uuid)
        if existing:
            return existing, True

    tx = deposit_advance(
        seller,
        customer,
        amount,
        payment_method=normalize_payment_method(payment_method, default='upi'),
        note=note,
        client_id=client_uuid,
        device_created_at=_parse_device_created_at(device_created_at),
    )
    return tx, False


def apply_advance_use_idempotent(
    seller,
    customer,
    amount,
    *,
    client_id=None,
    device_created_at=None,
    note='',
):
    client_uuid = _parse_client_uuid(client_id) if client_id else None
    if client_uuid:
        existing = find_transaction_by_client_id(seller, client_uuid)
        if existing:
            return existing, True

    try:
        tx = use_advance(
            seller,
            customer,
            amount,
            note=note,
            client_id=client_uuid,
            device_created_at=_parse_device_created_at(device_created_at),
        )
    except ValueError as exc:
        raise SyncError(str(exc), code='validation', status_code=422) from exc
    return tx, False


def write_result(customer, tx, *, duplicate=False, sms=None):
    data = {
        'duplicate': duplicate,
        'customer': customer_detail(customer),
    }
    if tx:
        data['transaction'] = transaction_item(tx)
    if sms is not None:
        data['sms'] = sms
    return data


def operation_result(client_id, *, status, server_id=None, duplicate=False, customer=None, transaction=None, error=None, code=None):
    row = {
        'client_id': str(client_id),
        'status': status,
        'duplicate': duplicate,
    }
    if server_id:
        row['server_id'] = str(server_id)
    if customer:
        row['customer'] = customer_detail(customer)
    if transaction:
        row['transaction'] = transaction_item(transaction)
    if error:
        row['error'] = error
    if code:
        row['code'] = code
    return row


@transaction.atomic
def push_sync(seller, operations):
    id_map = {}
    results = []

    for raw_op in operations:
        client_id = raw_op.get('client_id')
        op = raw_op.get('op', '')
        payload = raw_op.get('payload') or {}

        if not client_id:
            results.append(
                operation_result(
                    '',
                    status='failed',
                    error='client_id is required',
                    code='validation',
                )
            )
            continue

        try:
            result = _process_operation(seller, op, payload, client_id, id_map)
            results.append(result)
            if result.get('status') == 'ok' and result.get('server_id'):
                normalized = normalize_client_id(client_id)
                key = normalized or str(client_id)
                id_map[key] = result['server_id']
                id_map[f'local:{key}'] = result['server_id']
                if op == 'create_customer' or _normalize_sync_op(op) == 'create_customer':
                    server_customer_id = str(result['customer']['id'])
                    id_map[key] = server_customer_id
                    id_map[f'local:{key}'] = server_customer_id
        except SyncError as exc:
            results.append(
                operation_result(
                    client_id,
                    status='failed',
                    error=exc.message,
                    code=exc.code,
                )
            )
        except Exception as exc:
            results.append(
                operation_result(
                    client_id,
                    status='failed',
                    error=str(exc),
                    code='error',
                )
            )

    return {
        'synced_at': timezone.now().isoformat(),
        'id_map': id_map,
        'results': results,
    }


def _normalize_sync_op(op):
    text = (op or '').strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'createcustomer': 'create_customer',
        'customer_create': 'create_customer',
        'addcustomer': 'create_customer',
        'add_credit': 'credit',
        'addcredit': 'credit',
        'receive': 'receive_payment',
        'receivepayment': 'receive_payment',
        'payment': 'receive_payment',
        'advancedeposit': 'advance_deposit',
        'advance_use': 'advance_use',
        'advanceuse': 'advance_use',
    }
    return aliases.get(text, text)


def _process_operation(seller, op, payload, client_id, id_map):
    op = _normalize_sync_op(op)
    if op == 'create_customer':
        customer, duplicate = create_customer_idempotent(
            seller,
            client_id=client_id,
            device_created_at=payload.get('device_created_at'),
            name=payload.get('name', ''),
            phone=payload.get('phone', ''),
            email=payload.get('email', ''),
            address=payload.get('address', ''),
            city=payload.get('city', ''),
            state=payload.get('state', ''),
            country=payload.get('country', 'India'),
        )
        return operation_result(
            client_id,
            status='ok',
            server_id=str(customer.id),
            duplicate=duplicate,
            customer=customer,
        )

    customer = resolve_customer(seller, payload, id_map)
    amount = payload.get('amount')
    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError):
        raise SyncError('amount is required and must be a number.', code='validation', status_code=422)

    if op in ('credit', 'add_credit'):
        tx, duplicate, _sms = apply_credit_idempotent(
            seller,
            customer,
            amount,
            client_id=client_id,
            device_created_at=payload.get('device_created_at'),
            note=payload.get('note', ''),
            send_sms=payload.get('send_sms'),
            due_date=payload.get('due_date'),
        )
    elif op in ('receive', 'receive_payment', 'payment'):
        tx, duplicate, _sms = apply_payment_idempotent(
            seller,
            customer,
            amount,
            client_id=client_id,
            device_created_at=payload.get('device_created_at'),
            payment_method=payload.get('payment_method', 'UPI'),
            note=payload.get('note', ''),
            send_sms=payload.get('send_sms'),
        )
    elif op in ('advance_deposit',):
        tx, duplicate = apply_advance_deposit_idempotent(
            seller,
            customer,
            amount,
            client_id=client_id,
            device_created_at=payload.get('device_created_at'),
            payment_method=payload.get('payment_method', 'UPI'),
            note=payload.get('note', ''),
        )
    elif op in ('advance_use',):
        tx, duplicate = apply_advance_use_idempotent(
            seller,
            customer,
            amount,
            client_id=client_id,
            device_created_at=payload.get('device_created_at'),
            note=payload.get('note', ''),
        )
    else:
        raise SyncError(f'Unknown op: {op}', code='validation', status_code=422)

    customer.refresh_from_db()
    return operation_result(
        client_id,
        status='ok',
        server_id=str(tx.id),
        duplicate=duplicate,
        customer=customer,
        transaction=tx,
    )


def pull_changes(seller, since=None):
    since_dt = parse_since(since) if since else None
    synced_at = timezone.now()

    customers_qs = SellerCustomer.objects.filter(seller=seller)
    txs_qs = LedgerTransaction.objects.filter(seller=seller).select_related('customer')

    if since_dt:
        customers_qs = customers_qs.filter(updated_at__gte=since_dt)
        txs_qs = txs_qs.filter(updated_at__gte=since_dt)

    unread_notifications = SellerNotification.objects.filter(
        seller=seller, is_read=False
    ).count()

    return {
        'synced_at': synced_at.isoformat(),
        'customers': [customer_list_item(c) for c in customers_qs.order_by('-updated_at')],
        'transactions': [transaction_item(tx) for tx in txs_qs.order_by('-updated_at')],
        'deleted_customer_ids': [],
        'unread_notifications_count': unread_notifications,
    }
