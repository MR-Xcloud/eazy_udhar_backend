from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from ..models import (
    RazorpayPayment,
    SellerSubscription,
    SubscriptionInvoice,
    SubscriptionPlan,
)
from ..permissions import RoleRequired
from ..services.download_tokens import make_invoice_download_token, verify_invoice_download_token
from ..services.gst import determine_tax_type
from ..services.invoice_pdf import (
    COMPANY_BANK_ACCOUNT_NO,
    COMPANY_BANK_NAME,
    COMPANY_EMAIL,
    COMPANY_NAME,
    ensure_invoice_pdf,
    tax_line_items,
)
from ..utils import log_audit

ADMIN_API_BASE = f"{(getattr(settings, 'PUBLIC_STATEMENT_BASE_URL', '') or '').rstrip('/')}/admin-api/v1"
from .base import AdminAPIView


def _subscription_item(sub):
    return {
        'id': sub.id,
        'seller_id': sub.seller_id,
        'seller_name': sub.seller.business_name,
        'plan_id': sub.plan_id,
        'plan_name': sub.plan.name,
        'status': sub.status,
        'billing_amount': float(sub.billing_amount),
        'currency': sub.currency,
        'current_period_start': sub.current_period_start.isoformat(),
        'current_period_end': sub.current_period_end.isoformat(),
        'trial_ends_at': sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        'razorpay_subscription_id': sub.razorpay_subscription_id or None,
    }


def _plan_item(plan):
    features = plan.features
    message_limit = int(features.get('message_limit', 0)) if isinstance(features, dict) else 0
    if isinstance(features, dict):
        features = features.get('items', []) or list(features.values())
    return {
        'id': plan.id,
        'name': plan.name,
        'slug': plan.slug,
        'price_monthly': float(plan.price_monthly),
        'price_yearly': float(plan.price_yearly),
        'trial_days': plan.trial_days,
        'message_limit': message_limit,
        'features': features if isinstance(features, list) else [],
        'is_active': plan.is_active,
        'sort_order': plan.sort_order,
    }


def _payment_item(payment):
    return {
        'id': payment.id,
        'seller_id': payment.seller_id,
        'order_id': payment.order_id,
        'payment_id': payment.payment_id,
        'amount': float(payment.amount),
        'currency': payment.currency,
        'status': payment.status,
        'method': payment.method or None,
        'created_at': payment.created_at.isoformat(),
        'refunded_at': payment.refunded_at.isoformat() if payment.refunded_at else None,
    }


def _invoice_item(invoice, detailed=False):
    item = {
        'id': invoice.id,
        'subscription_id': invoice.subscription_id,
        'seller_id': invoice.seller_id,
        'seller_name': invoice.seller.business_name,
        'invoice_number': invoice.invoice_number,
        'amount': float(invoice.amount),
        'tax_amount': float(invoice.tax_amount),
        'tax_type': invoice.tax_type,
        'total_amount': float(invoice.amount + invoice.tax_amount),
        'currency': invoice.subscription.currency,
        'status': invoice.status,
        'payment_method': invoice.payment_method,
        'offline_reference': invoice.offline_reference or None,
        'notes': invoice.notes or None,
        'recorded_by': invoice.recorded_by.full_name if invoice.recorded_by_id else None,
        'paid_at': invoice.paid_at.isoformat() if invoice.paid_at else None,
        'period_start': invoice.period_start.isoformat(),
        'period_end': invoice.period_end.isoformat(),
        'pdf_url': invoice.pdf_url or None,
        'seller_email': invoice.seller.email if getattr(invoice, 'seller', None) else None,
        'emailed_at': invoice.emailed_at.isoformat() if getattr(invoice, 'emailed_at', None) else None,
        'download_url': (
            f'{ADMIN_API_BASE}/subscriptions/invoices/{invoice.id}/download'
            f'?token={make_invoice_download_token(invoice.id)}'
        ),
        'created_at': invoice.created_at.isoformat(),
    }
    if detailed:
        item.update({
            'plan_name': invoice.subscription.plan.name,
            'seller_email': invoice.seller.email,
            'seller_phone': invoice.seller.phone,
            'seller_gst_number': invoice.seller.gst_number or None,
        })
    return item


def _next_invoice_number():
    """INV-YYYYMM-#### sequential within the month, e.g. INV-202607-0001."""
    now = timezone.now()
    prefix = f'INV-{now:%Y%m}-'
    count = SubscriptionInvoice.objects.filter(invoice_number__startswith=prefix).count()
    return f'{prefix}{count + 1:04d}'


class SubscriptionListView(AdminAPIView):
    def get(self, request):
        qs = SellerSubscription.objects.select_related('seller', 'plan').order_by('-created_at')
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(seller__business_name__icontains=search)
                | Q(seller__email__icontains=search)
                | Q(plan__name__icontains=search)
            )
        page, paginator = self.paginate(request, qs)
        data = [_subscription_item(s) for s in page]
        return paginator.get_paginated_response(data)


class SubscriptionCancelView(AdminAPIView):
    def post(self, request, pk):
        try:
            sub = SellerSubscription.objects.get(pk=pk)
        except SellerSubscription.DoesNotExist:
            return Response({'detail': 'Subscription not found.'}, status=status.HTTP_404_NOT_FOUND)
        sub.status = SellerSubscription.STATUS_CANCELLED
        sub.save(update_fields=['status'])
        log_audit(request.user, 'subscription_cancel', 'subscription', sub.pk, request=request)
        return Response(_subscription_item(sub))


class SubscriptionPatchView(AdminAPIView):
    def patch(self, request, pk):
        try:
            sub = SellerSubscription.objects.select_related('seller', 'plan').get(pk=pk)
        except SellerSubscription.DoesNotExist:
            return Response({'detail': 'Subscription not found.'}, status=status.HTTP_404_NOT_FOUND)
        plan_id = request.data.get('plan_id')
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(pk=plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)
            sub.plan = plan
            sub.billing_amount = plan.price_monthly
            sub.save(update_fields=['plan', 'billing_amount'])
            log_audit(request.user, 'plan_change', 'subscription', sub.pk, {'plan_id': plan_id}, request)
        return Response(_subscription_item(sub))


class SubscriptionPlanListView(AdminAPIView):
    def get(self, request):
        plans = SubscriptionPlan.objects.order_by('sort_order', 'name')
        return Response({'data': [_plan_item(p) for p in plans]})

    def get_permissions(self):
        from ..models import AdminUser

        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method == 'POST':
            perms.append(RoleRequired([AdminUser.ROLE_SUPER_ADMIN]))
        return perms

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        slug = (request.data.get('slug') or '').strip()
        if not name or not slug:
            return Response({'detail': 'Name and slug are required.'}, status=status.HTTP_400_BAD_REQUEST)
        features = request.data.get('features', {})
        if not isinstance(features, dict):
            features = {}
        if 'message_limit' in request.data:
            try:
                features['message_limit'] = int(request.data.get('message_limit') or 0)
            except (TypeError, ValueError):
                features['message_limit'] = 0
        plan = SubscriptionPlan.objects.create(
            name=name,
            slug=slug,
            price_monthly=request.data.get('price_monthly', 0),
            price_yearly=request.data.get('price_yearly', 0),
            trial_days=request.data.get('trial_days', 0),
            features=features,
            is_active=request.data.get('is_active', True),
            sort_order=request.data.get('sort_order', 0),
        )
        log_audit(request.user, 'plan_create', 'plan', plan.pk, request=request)
        return Response(_plan_item(plan), status=status.HTTP_201_CREATED)


class SubscriptionPlanDetailView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN])
        ]

    def patch(self, request, pk):
        try:
            plan = SubscriptionPlan.objects.get(pk=pk)
        except SubscriptionPlan.DoesNotExist:
            return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        for field in ('name', 'slug', 'price_monthly', 'price_yearly', 'trial_days', 'features', 'is_active', 'sort_order'):
            if field in request.data:
                setattr(plan, field, request.data[field])
        if 'message_limit' in request.data:
            features = plan.features if isinstance(plan.features, dict) else {}
            try:
                features['message_limit'] = int(request.data.get('message_limit') or 0)
            except (TypeError, ValueError):
                pass
            plan.features = features
        plan.save()
        log_audit(request.user, 'plan_update', 'plan', plan.pk, request=request)
        return Response(_plan_item(plan))

    def delete(self, request, pk):
        try:
            plan = SubscriptionPlan.objects.get(pk=pk)
        except SubscriptionPlan.DoesNotExist:
            return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        plan.is_active = False
        plan.save(update_fields=['is_active'])
        log_audit(request.user, 'plan_deactivate', 'plan', plan.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TrialListView(AdminAPIView):
    def get(self, request):
        qs = SellerSubscription.objects.filter(
            status=SellerSubscription.STATUS_TRIAL
        ).select_related('seller', 'plan').order_by('trial_ends_at')
        expiring_days = request.query_params.get('expiring_in_days')
        if expiring_days:
            try:
                days = int(expiring_days)
                cutoff = timezone.now() + timedelta(days=days)
                qs = qs.filter(trial_ends_at__lte=cutoff)
            except ValueError:
                pass
        page, paginator = self.paginate(request, qs)
        data = [_subscription_item(s) for s in page]
        return paginator.get_paginated_response(data)


class TrialExtendView(AdminAPIView):
    def post(self, request, pk):
        try:
            sub = SellerSubscription.objects.select_related('seller', 'plan').get(pk=pk)
        except SellerSubscription.DoesNotExist:
            return Response({'detail': 'Trial not found.'}, status=status.HTTP_404_NOT_FOUND)
        if sub.status != SellerSubscription.STATUS_TRIAL:
            return Response({'detail': 'Subscription is not on trial.'}, status=status.HTTP_400_BAD_REQUEST)
        days = int(request.data.get('days', 7))
        sub.trial_ends_at = (sub.trial_ends_at or timezone.now()) + timedelta(days=days)
        sub.current_period_end = sub.trial_ends_at
        sub.save(update_fields=['trial_ends_at', 'current_period_end'])
        log_audit(request.user, 'trial_extend', 'subscription', sub.pk, {'days': days}, request)
        return Response(_subscription_item(sub))


class TrialConvertView(AdminAPIView):
    def post(self, request, pk):
        try:
            sub = SellerSubscription.objects.select_related('seller', 'plan').get(pk=pk)
        except SellerSubscription.DoesNotExist:
            return Response({'detail': 'Trial not found.'}, status=status.HTTP_404_NOT_FOUND)
        plan_id = request.data.get('plan_id')
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(pk=plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)
            sub.plan = plan
            sub.billing_amount = plan.price_monthly
        now = timezone.now()
        sub.status = SellerSubscription.STATUS_ACTIVE
        sub.trial_ends_at = None
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
        sub.save()
        log_audit(request.user, 'trial_convert', 'subscription', sub.pk, request=request)
        return Response(_subscription_item(sub))


class TrialExpireView(AdminAPIView):
    def post(self, request, pk):
        try:
            sub = SellerSubscription.objects.select_related('seller', 'plan').get(pk=pk)
        except SellerSubscription.DoesNotExist:
            return Response({'detail': 'Trial not found.'}, status=status.HTTP_404_NOT_FOUND)
        sub.status = SellerSubscription.STATUS_EXPIRED
        sub.save(update_fields=['status'])
        log_audit(request.user, 'trial_expire', 'subscription', sub.pk, request=request)
        return Response(_subscription_item(sub))


class PaymentListView(AdminAPIView):
    def get(self, request):
        qs = RazorpayPayment.objects.select_related('seller').order_by('-created_at')
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        page, paginator = self.paginate(request, qs)
        data = [_payment_item(p) for p in page]
        return paginator.get_paginated_response(data)


class PaymentRefundView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_FINANCE, AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, pk):
        try:
            payment = RazorpayPayment.objects.get(pk=pk)
        except RazorpayPayment.DoesNotExist:
            return Response({'detail': 'Payment not found.'}, status=status.HTTP_404_NOT_FOUND)
        if payment.refunded_at:
            return Response({'detail': 'Payment already refunded.'}, status=status.HTTP_400_BAD_REQUEST)
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': 'Reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
        payment.status = 'refunded'
        payment.refunded_at = timezone.now()
        payment.refund_reason = reason
        payment.save(update_fields=['status', 'refunded_at', 'refund_reason'])
        log_audit(request.user, 'refund', 'payment', payment.pk, {'reason': reason}, request)
        return Response(_payment_item(payment))


class InvoiceListView(AdminAPIView):
    def get(self, request):
        qs = SubscriptionInvoice.objects.select_related('subscription', 'seller').order_by('-created_at')
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        payment_method = request.query_params.get('payment_method')
        if payment_method:
            qs = qs.filter(payment_method=payment_method)
        page, paginator = self.paginate(request, qs)
        data = [_invoice_item(inv) for inv in page]
        return paginator.get_paginated_response(data)

    def get_permissions(self):
        from ..models import AdminUser

        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method == 'POST':
            perms.append(RoleRequired([AdminUser.ROLE_FINANCE, AdminUser.ROLE_SUPER_ADMIN]))
        return perms

    def post(self, request):
        """Manually record an invoice — used for offline payments (cash/UPI/bank
        transfer) from sellers who don't pay through Razorpay."""
        subscription_id = request.data.get('subscription_id')
        try:
            sub = SellerSubscription.objects.select_related('seller').get(pk=subscription_id)
        except (SellerSubscription.DoesNotExist, TypeError, ValueError):
            return Response({'detail': 'Subscription not found.'}, status=status.HTTP_404_NOT_FOUND)

        payment_method = request.data.get('payment_method', SubscriptionInvoice.PAYMENT_METHOD_OFFLINE)
        if payment_method not in dict(SubscriptionInvoice.PAYMENT_METHOD_CHOICES):
            return Response({'detail': 'Invalid payment_method.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = request.data.get('amount', sub.billing_amount)
            tax_amount = request.data.get('tax_amount', 0)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid amount.'}, status=status.HTTP_400_BAD_REQUEST)

        is_offline = payment_method == SubscriptionInvoice.PAYMENT_METHOD_OFFLINE
        if is_offline and not (request.data.get('offline_reference') or '').strip():
            return Response(
                {'detail': 'offline_reference is required to record an offline payment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        invoice = SubscriptionInvoice.objects.create(
            subscription=sub,
            seller=sub.seller,
            invoice_number=_next_invoice_number(),
            amount=amount,
            tax_amount=tax_amount,
            tax_type=determine_tax_type(sub.seller.gst_number),
            status=SubscriptionInvoice.STATUS_PAID if is_offline else SubscriptionInvoice.STATUS_DRAFT,
            payment_method=payment_method,
            offline_reference=(request.data.get('offline_reference') or '').strip(),
            notes=(request.data.get('notes') or '').strip(),
            recorded_by=request.user,
            paid_at=now if is_offline else None,
            period_start=sub.current_period_start,
            period_end=sub.current_period_end,
        )
        log_audit(
            request.user,
            'invoice_record_offline' if is_offline else 'invoice_create',
            'invoice',
            invoice.pk,
            {'payment_method': payment_method, 'amount': str(amount)},
            request,
        )
        ensure_invoice_pdf(invoice)
        return Response(_invoice_item(invoice, detailed=True), status=status.HTTP_201_CREATED)


class InvoiceDetailView(AdminAPIView):
    def get(self, request, pk):
        try:
            invoice = SubscriptionInvoice.objects.select_related(
                'subscription__plan', 'seller'
            ).get(pk=pk)
        except SubscriptionInvoice.DoesNotExist:
            return Response({'detail': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_invoice_item(invoice, detailed=True))


class InvoiceSendEmailView(AdminAPIView):
    def post(self, request, pk):
        try:
            invoice = SubscriptionInvoice.objects.select_related(
                'subscription__plan', 'seller'
            ).get(pk=pk)
        except SubscriptionInvoice.DoesNotExist:
            return Response({'detail': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)

        from customerapp.email_otp import send_invoice_email

        seller = invoice.seller
        if not seller.email:
            return Response({'detail': 'This seller has no email on file.'}, status=status.HTTP_400_BAD_REQUEST)

        sub = invoice.subscription
        # Permanent, unauthenticated /media/ link — unlike the signed
        # download_url used in the admin panel, an emailed link needs to keep
        # working whenever the recipient eventually opens the email.
        download_url = ensure_invoice_pdf(invoice)
        result = send_invoice_email(
            to_email=seller.email,
            business_name=seller.business_name,
            invoice_number=invoice.invoice_number,
            amount=invoice.amount,
            tax_lines=tax_line_items(invoice),
            total_amount=invoice.amount + invoice.tax_amount,
            status_label=invoice.get_status_display(),
            plan_name=sub.plan.name,
            period_start=invoice.period_start.strftime('%d %b %Y'),
            period_end=invoice.period_end.strftime('%d %b %Y'),
            payment_method_label=invoice.get_payment_method_display(),
            offline_reference=invoice.offline_reference or None,
            download_url=download_url,
            bank_name=COMPANY_BANK_NAME,
            bank_account_no=COMPANY_BANK_ACCOUNT_NO,
            support_email=COMPANY_EMAIL,
            company_name=COMPANY_NAME,
        )
        if not result['sent']:
            return Response({'detail': result.get('error') or 'Could not send email.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        invoice.emailed_at = timezone.now()
        invoice.save(update_fields=['emailed_at'])
        log_audit(request.user, 'invoice_email_sent', 'invoice', invoice.pk, {'to': seller.email}, request)
        return Response({
            'detail': f'Invoice emailed to {seller.email}.',
            'to': seller.email,
            'emailed_at': invoice.emailed_at.isoformat(),
        })


class InvoiceDownloadView(AdminAPIView):
    """Plain browser navigation (clicking a link / opening a new tab) can't
    attach the Authorization: Bearer header the rest of the admin API needs,
    so this endpoint also accepts a signed, time-limited `?token=` — see
    `download_url` on the invoice item, which is the one admin-panel links
    should use. The bare header-based auth still works too, for programmatic
    callers."""

    def get_permissions(self):
        token = self.request.query_params.get('token')
        if verify_invoice_download_token(token, self.kwargs.get('pk')):
            return []
        return [perm() for perm in AdminAPIView.permission_classes]

    def get(self, request, pk):
        try:
            invoice = SubscriptionInvoice.objects.select_related(
                'subscription__plan', 'seller'
            ).get(pk=pk)
        except SubscriptionInvoice.DoesNotExist:
            return Response({'detail': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)
        url = ensure_invoice_pdf(invoice)
        return HttpResponseRedirect(url)
