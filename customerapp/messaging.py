from customerapp.models import Customer, CustomerAccount, CustomerNotification, ShopMessage
from sellerapp.models import SellerCustomer


def normalize_phone(phone):
    """Digits only; for Indian numbers use last 10 digits so +91 matches local."""
    if not phone:
        return ''
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def phones_match(phone_a, phone_b):
    a = normalize_phone(phone_a)
    b = normalize_phone(phone_b)
    return bool(a) and a == b


def find_customer_user_by_phone(phone):
    norm = normalize_phone(phone)
    if not norm:
        return None
    for user in Customer.objects.all().only('id', 'phone', 'email'):
        if phones_match(user.phone, phone):
            return user
    return None


def find_customer_user_by_email(email):
    if not email:
        return None
    try:
        return Customer.objects.get(email__iexact=email.strip())
    except Customer.DoesNotExist:
        return None


def link_seller_customer(seller_customer):
    """Link SellerCustomer to registered Customer user by phone or email."""
    if seller_customer.linked_customer_id:
        user = seller_customer.linked_customer
        ensure_customer_account(seller_customer, user)
        return user

    user = find_customer_user_by_phone(seller_customer.phone)
    if not user and seller_customer.email:
        user = find_customer_user_by_email(seller_customer.email)
    if user:
        seller_customer.linked_customer = user
        seller_customer.save(update_fields=['linked_customer', 'updated_at'])
        ensure_customer_account(seller_customer, user)
    return user


def sync_customer_from_seller_ledgers(customer_user):
    """Link all seller ledger rows that match this customer's phone/email."""
    linked_accounts = []
    for sc in SellerCustomer.objects.select_related('seller').all():
        phone_match = phones_match(sc.phone, customer_user.phone)
        email_match = (
            sc.email
            and customer_user.email
            and sc.email.lower() == customer_user.email.lower()
        )
        if phone_match or email_match:
            user = link_seller_customer(sc)
            if user and user.id == customer_user.id:
                account = ensure_customer_account(sc, user)
                linked_accounts.append(account)
                _backfill_messages_for_thread(sc, user, account)
    return linked_accounts


def ensure_customer_account(seller_customer, customer_user):
    """Ensure CustomerAccount exists and is linked to this seller customer."""
    account = CustomerAccount.objects.filter(
        user=customer_user,
        seller_customer=seller_customer,
    ).first()
    if account:
        account.seller = seller_customer.seller
        account.shop_name = seller_customer.seller.business_name
        account.outstanding_amount = seller_customer.outstanding_amount
        account.advance_deposited = seller_customer.advance_deposited
        account.advance_used = seller_customer.advance_used
        account.status = _map_status(seller_customer.status)
        account.has_balance = seller_customer.outstanding_amount > 0
        account.save()
        return account

    account = CustomerAccount.objects.filter(
        user=customer_user,
        shop_name=seller_customer.seller.business_name,
    ).first()
    if account:
        account.seller = seller_customer.seller
        account.seller_customer = seller_customer
        account.outstanding_amount = seller_customer.outstanding_amount
        account.advance_deposited = seller_customer.advance_deposited
        account.advance_used = seller_customer.advance_used
        account.save()
        return account

    return CustomerAccount.objects.create(
        user=customer_user,
        shop_name=seller_customer.seller.business_name,
        seller=seller_customer.seller,
        seller_customer=seller_customer,
        outstanding_amount=seller_customer.outstanding_amount,
        advance_deposited=seller_customer.advance_deposited,
        advance_used=seller_customer.advance_used,
        status=_map_status(seller_customer.status),
        has_balance=seller_customer.outstanding_amount > 0,
    )


def _map_status(seller_status):
    mapping = {
        'overdue': CustomerAccount.STATUS_OVERDUE,
        'settled': CustomerAccount.STATUS_CLEARED,
        'paid': CustomerAccount.STATUS_CLEARED,
    }
    return mapping.get(seller_status, CustomerAccount.STATUS_ACTIVE)


def _backfill_messages_for_thread(seller_customer, customer_user, account):
    """Attach orphaned messages and create missing notifications."""
    from django.db.models import Q

    orphaned = ShopMessage.objects.filter(seller_customer=seller_customer).filter(
        Q(customer_user__isnull=True) | ~Q(customer_user=customer_user)
    )
    for msg in orphaned:
        msg.customer_user = customer_user
        msg.customer_account = account
        msg.save(update_fields=['customer_user', 'customer_account'])

    seller = seller_customer.seller
    for msg in ShopMessage.objects.filter(
        seller_customer=seller_customer,
        sender=ShopMessage.SENDER_SELLER,
        customer_user=customer_user,
    ):
        exists = CustomerNotification.objects.filter(
            user=customer_user,
            reference_id=str(msg.id),
        ).exists()
        if not exists:
            notify_customer_message(customer_user, account, msg, seller.business_name)


def resolve_account_for_shop(customer_user, shop_id):
    account = CustomerAccount.objects.select_related(
        'seller', 'seller_customer', 'seller_customer__seller'
    ).get(id=shop_id, user=customer_user)
    if account.seller_customer_id:
        link_seller_customer(account.seller_customer)
    return account


def get_thread_messages(*, seller_customer, customer_user=None):
    """All messages for a seller–customer thread (not filtered by user id)."""
    return ShopMessage.objects.filter(
        seller_customer=seller_customer,
    ).select_related('seller').order_by('created_at')


def build_absolute_file_url(request, file_field):
    if not file_field:
        return None
    try:
        url = file_field.url
    except ValueError:
        return None
    if request:
        return request.build_absolute_uri(url)
    return url


def message_to_dict(message, request=None):
    return {
        'id': str(message.id),
        'sender': message.sender,
        'message': message.message or '',
        'image_url': build_absolute_file_url(request, message.attachment),
        'created_at': message.created_at.isoformat(),
    }


def notify_customer_message(customer_user, account, message, shop_name):
    if not customer_user:
        return None
    subtitle = (message.message or '')[:80]
    if not subtitle and message.attachment:
        subtitle = 'Sent an image'
    notification = CustomerNotification.objects.create(
        user=customer_user,
        notification_type=CustomerNotification.TYPE_MESSAGE,
        title=f'New message from {shop_name}',
        subtitle=subtitle,
        shop_account=account,
        reference_id=str(message.id),
        is_read=False,
    )
    from easyudhar.fcm import push_customer_notification

    push_customer_notification(notification)
    return notification


def notify_customer_event(
    customer_user,
    account,
    *,
    notification_type,
    title,
    subtitle,
    reference_id='',
):
    if not customer_user or not account:
        return None
    notification = CustomerNotification.objects.create(
        user=customer_user,
        notification_type=notification_type,
        title=title,
        subtitle=subtitle[:500],
        shop_account=account,
        reference_id=reference_id,
        is_read=False,
    )
    from easyudhar.fcm import push_customer_notification

    push_customer_notification(notification)
    return notification


def notify_customer_added_by_seller(seller_customer, seller):
    """Notify registered customer when a seller adds them to their ledger."""
    customer_user = link_seller_customer(seller_customer)
    if not customer_user:
        return None
    account = ensure_customer_account(seller_customer, customer_user)
    shop_name = seller.business_name or 'A shop'
    return notify_customer_event(
        customer_user,
        account,
        notification_type=CustomerNotification.TYPE_GENERAL,
        title=f'{shop_name} added you as a customer',
        subtitle='View your account balance and messages in the app',
        reference_id=str(seller_customer.id),
    )


def send_seller_message(
    seller,
    seller_customer,
    *,
    text='',
    attachment=None,
    request=None,
    notify=True,
):
    customer_user = link_seller_customer(seller_customer)
    account = None
    if customer_user:
        account = ensure_customer_account(seller_customer, customer_user)

    message = ShopMessage.objects.create(
        seller=seller,
        seller_customer=seller_customer,
        customer_user=customer_user,
        customer_account=account,
        sender=ShopMessage.SENDER_SELLER,
        message=text or '',
        attachment=attachment,
    )

    if notify and customer_user and account:
        notify_customer_message(
            customer_user,
            account,
            message,
            seller.business_name,
        )
    return message


def send_customer_message(customer_user, account, *, text='', attachment=None, request=None):
    from sellerapp.notifications import notify_seller_message

    seller_customer = account.seller_customer
    if not seller_customer:
        raise ValueError('This shop account is not linked to a seller customer.')

    message = ShopMessage.objects.create(
        seller=seller_customer.seller,
        seller_customer=seller_customer,
        customer_user=customer_user,
        customer_account=account,
        sender=ShopMessage.SENDER_CUSTOMER,
        message=text or '',
        attachment=attachment,
    )
    notify_seller_message(seller_customer.seller, seller_customer, message)
    return message
