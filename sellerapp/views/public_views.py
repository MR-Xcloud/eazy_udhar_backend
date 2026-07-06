from django.shortcuts import get_object_or_404, render
from django.views import View

from ..daily_sms import (
    digests_for_phone,
    get_all_customer_transactions,
    get_customer_lifetime_summary,
    get_digest_transactions,
)
from ..models import CustomerDayDigest, CustomerNightlyDigest, LedgerTransaction
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
    timestamp = (
        tx.created_at.strftime('%d %b %Y, %I:%M %p')
        if include_date
        else tx.created_at.strftime('%I:%M %p')
    )
    return {
        'time': timestamp,
        'date_label': tx.created_at.strftime('%d %b %Y'),
        'label': _transaction_label(tx),
        'note': tx.note,
        'amount_display': format_inr_signed(tx.amount, positive=positive),
        'payment_method': tx.payment_method or '',
    }


class ShortStatementPublicView(View):
    """Public statement via SMS short link: https://api.eazyudhar.com/s/<code>"""

    def get(self, request, code):
        nightly = CustomerNightlyDigest.objects.filter(short_code=code).first()
        if nightly:
            return DayStatementPublicView()._render_merged(request, nightly)

        digest = (
            CustomerDayDigest.objects.select_related(
                'seller_customer',
                'seller_customer__seller',
            )
            .filter(short_code=code)
            .first()
        )
        if digest:
            return DayStatementPublicView()._render_single(request, digest)

        from django.http import Http404

        raise Http404('Statement link not found or expired.')


class DayStatementPublicView(View):
    """Public account statement: https://eazy-udhar-backend.onrender.com/<token>"""

    def get(self, request, token):
        nightly = CustomerNightlyDigest.objects.filter(token=token).first()
        if not nightly:
            nightly = CustomerNightlyDigest.objects.filter(short_code=token).first()
        if nightly:
            return self._render_merged(request, nightly)

        digest = CustomerDayDigest.objects.select_related(
            'seller_customer',
            'seller_customer__seller',
        ).filter(token=token).first()
        if not digest:
            digest = (
                CustomerDayDigest.objects.select_related(
                    'seller_customer',
                    'seller_customer__seller',
                )
                .filter(short_code=token)
                .first()
            )
        if not digest:
            from django.http import Http404

            raise Http404('Statement link not found or expired.')
        return self._render_single(request, digest)

    def _render_merged(self, request, nightly):
        digests = digests_for_phone(nightly.activity_date, nightly.phone)
        if not digests:
            return render(
                request,
                'sellerapp/merged_day_statement.html',
                {'empty': True},
                status=404,
            )

        shops = []
        day_credit = day_payment = day_txn_count = 0
        customer_name = digests[0].seller_customer.name

        for digest in digests:
            customer = digest.seller_customer
            seller = customer.seller
            lifetime = get_customer_lifetime_summary(customer)
            today_transactions = get_digest_transactions(digest)
            day_credit += digest.credit_total
            day_payment += digest.payment_total
            day_txn_count += digest.transaction_count
            shops.append(
                {
                    'shop_name': seller.business_name,
                    'customer_name': customer.name,
                    'lifetime': {
                        'total_credit': format_inr(lifetime['total_credit']),
                        'total_payment': format_inr(lifetime['total_payment']),
                        'outstanding': format_inr(lifetime['outstanding']),
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
                        _transaction_line(tx, include_date=True)
                        for tx in get_all_customer_transactions(customer)
                    ],
                }
            )

        context = {
            'empty': False,
            'merged': True,
            'customer_name': customer_name,
            'activity_date': nightly.activity_date.strftime('%d %b %Y'),
            'day_totals': {
                'credit_total': format_inr(day_credit),
                'payment_total': format_inr(day_payment),
                'transaction_count': day_txn_count,
                'shop_count': len(shops),
            },
            'shops': shops,
        }
        return render(request, 'sellerapp/merged_day_statement.html', context)

    def _render_single(self, request, digest):
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
