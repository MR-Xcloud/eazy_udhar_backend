from .models import SellerNotification


def _push_seller(notification):
    from easyudhar.fcm import push_seller_notification

    push_seller_notification(notification)


def notify_seller_message(seller, seller_customer, message):
    customer_name = seller_customer.name
    subtitle = (message.message or '')[:80]
    if not subtitle and message.attachment:
        subtitle = 'Sent an image'
    notification = SellerNotification.objects.create(
        seller=seller,
        seller_customer=seller_customer,
        notification_type=SellerNotification.TYPE_MESSAGE,
        title=f'New message from {customer_name}',
        subtitle=subtitle,
        reference_id=str(message.id),
        is_read=False,
    )
    _push_seller(notification)
    return notification


def notify_seller_payment(seller, seller_customer, amount, method, reference_id=''):
    notification = SellerNotification.objects.create(
        seller=seller,
        seller_customer=seller_customer,
        notification_type=SellerNotification.TYPE_PAYMENT,
        title=f'Payment received from {seller_customer.name}',
        subtitle=f'Rs. {amount} via {method}',
        reference_id=reference_id,
        is_read=False,
    )
    _push_seller(notification)
    return notification


def notify_seller_credit(seller, seller_customer, amount, reference_id=''):
    notification = SellerNotification.objects.create(
        seller=seller,
        seller_customer=seller_customer,
        notification_type=SellerNotification.TYPE_CREDIT,
        title=f'Credit added for {seller_customer.name}',
        subtitle=f'Rs. {amount} added to account',
        reference_id=reference_id,
        is_read=False,
    )
    _push_seller(notification)
    return notification


def notify_seller_general(
    seller,
    *,
    title,
    subtitle='',
    notification_type=SellerNotification.TYPE_GENERAL,
    seller_customer=None,
    reference_id='',
):
    notification = SellerNotification.objects.create(
        seller=seller,
        seller_customer=seller_customer,
        notification_type=notification_type,
        title=title,
        subtitle=subtitle[:500],
        reference_id=reference_id,
        is_read=False,
    )
    _push_seller(notification)
    return notification
