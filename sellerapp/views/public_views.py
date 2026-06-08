from django.shortcuts import get_object_or_404, render
from django.views import View

from ..daily_sms import (
    get_all_customer_transactions,
    get_customer_lifetime_summary,
    get_digest_transactions,
)
from ..models import CustomerDayDigest, LedgerTransaction
from ..utils import format_inr, format_inr_signed


def _transaction_label(tx):
    labels = {
        LedgerTransaction.TYPE_CREDIT: 'Credit added',
        LedgerTransaction.TYPE_PAYMENT: 'Payment received',
        LedgerTransaction.TYPE_ADVANCE_DEPOSIT: 'Advance deposit',
        LedgerTransaction.TYPE_ADVANCE_USE: 'Advance purchase',
    }
    return labels.get(tx.transaction_type, tx.transaction_type)


def _transaction_positive(tx):
    return tx.transaction_type in (
        LedgerTransaction.TYPE_CREDIT,
        LedgerTransaction.TYPE_ADVANCE_DEPOSIT,
    )


def _transaction_line(tx, *, include_date=False):
    positive = _transaction_positive(tx)
    timestamp = tx.created_at.strftime('%d %b %Y, %I:%M %p') if include_date else tx.created_at.strftime('%I:%M %p')
    return {
        'time': timestamp,
        'date_label': tx.created_at.strftime('%d %b %Y'),
        'label': _transaction_label(tx),
        'note': tx.note,
        'amount_display': format_inr_signed(tx.amount, positive=positive),
        'payment_method': tx.payment_method or '',
    }


class DayStatementPublicView(View):
    """Public account statement: https://eazy-udhar-backend.onrender.com/<token>"""

    def get(self, request, token):
        digest = get_object_or_404(
            CustomerDayDigest.objects.select_related(
                'seller_customer',
                'seller_customer__seller',
            ),
            token=token,
        )
        customer = digest.seller_customer
        seller = customer.seller
        lifetime = get_customer_lifetime_summary(customer)
        all_transactions = get_all_customer_transactions(customer)
        today_transactions = get_digest_transactions(digest)

        if lifetime['transaction_count'] == 0:
            return render(
                request,
                'sellerapp/day_statement.html',
                {
                    'customer_name': customer.name,
                    'shop_name': seller.business_name,
                    'empty': True,
                },
                status=404,
            )

        context = {
            'customer_name': customer.name,
            'shop_name': seller.business_name,
            'activity_date': digest.activity_date.strftime('%d %b %Y'),
            'empty': False,
            'lifetime': {
                'total_credit': format_inr(lifetime['total_credit']),
                'total_payment': format_inr(lifetime['total_payment']),
                'outstanding': format_inr(lifetime['outstanding']),
                'advance_deposited': format_inr(lifetime['total_advance_deposited']),
                'advance_used': format_inr(lifetime['total_advance_used']),
                'advance_balance': format_inr(lifetime['advance_balance']),
                'transaction_count': lifetime['transaction_count'],
            },
            'today': {
                'credit_total': format_inr(digest.credit_total),
                'payment_total': format_inr(digest.payment_total),
                'transaction_count': digest.transaction_count,
                'transactions': [_transaction_line(tx) for tx in today_transactions],
            },
            'all_transactions': [
                _transaction_line(tx, include_date=True) for tx in all_transactions
            ],
        }
        return render(request, 'sellerapp/day_statement.html', context)
