from django.utils import timezone

from customerapp.models import Customer
from sellerapp.models import Seller

from adminapp.models import AccountSuspension
from adminapp.utils import log_audit


def suspend_account(admin, *, account_type, account, reason, request=None):
    account.is_active = False
    account.save(update_fields=['is_active'])

    name = (
        account.business_name
        if account_type == AccountSuspension.ACCOUNT_SELLER
        else (account.full_name or account.email)
    )
    AccountSuspension.objects.filter(
        account_type=account_type,
        is_active=True,
        **(
            {'seller': account}
            if account_type == AccountSuspension.ACCOUNT_SELLER
            else {'customer': account}
        ),
    ).update(is_active=False, lifted_at=timezone.now())

    suspension = AccountSuspension.objects.create(
        account_type=account_type,
        seller=account if account_type == AccountSuspension.ACCOUNT_SELLER else None,
        customer=account if account_type == AccountSuspension.ACCOUNT_CUSTOMER else None,
        account_name=name,
        reason=reason,
        suspended_by=admin,
        is_active=True,
    )
    log_audit(
        admin,
        'suspend',
        account_type,
        account.pk,
        {'reason': reason},
        request=request,
    )
    return suspension


def unsuspend_account(admin, *, account_type, account, reason='', request=None):
    account.is_active = True
    account.save(update_fields=['is_active'])

    AccountSuspension.objects.filter(
        account_type=account_type,
        is_active=True,
        **(
            {'seller': account}
            if account_type == AccountSuspension.ACCOUNT_SELLER
            else {'customer': account}
        ),
    ).update(is_active=False, lifted_at=timezone.now())

    log_audit(
        admin,
        'unsuspend',
        account_type,
        account.pk,
        {'reason': reason},
        request=request,
    )


def get_seller_or_404(seller_id):
    return Seller.objects.get(pk=seller_id)


def get_customer_or_404(customer_id):
    return Customer.objects.get(pk=customer_id)
