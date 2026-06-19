from datetime import timedelta

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
from ..utils import log_audit
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
    if isinstance(features, dict):
        features = features.get('items', []) or list(features.values())
    return {
        'id': plan.id,
        'name': plan.name,
        'slug': plan.slug,
        'price_monthly': float(plan.price_monthly),
        'price_yearly': float(plan.price_yearly),
        'trial_days': plan.trial_days,
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


def _invoice_item(invoice):
    return {
        'id': invoice.id,
        'subscription_id': invoice.subscription_id,
        'seller_id': invoice.seller_id,
        'invoice_number': invoice.invoice_number,
        'amount': float(invoice.amount),
        'tax_amount': float(invoice.tax_amount),
        'status': invoice.status,
        'period_start': invoice.period_start.isoformat(),
        'period_end': invoice.period_end.isoformat(),
        'pdf_url': invoice.pdf_url or None,
        'created_at': invoice.created_at.isoformat(),
    }


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
        plan = SubscriptionPlan.objects.create(
            name=name,
            slug=slug,
            price_monthly=request.data.get('price_monthly', 0),
            price_yearly=request.data.get('price_yearly', 0),
            trial_days=request.data.get('trial_days', 0),
            features=request.data.get('features', {}),
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
        page, paginator = self.paginate(request, qs)
        data = [_invoice_item(inv) for inv in page]
        return paginator.get_paginated_response(data)


class InvoiceDownloadView(AdminAPIView):
    def get(self, request, pk):
        try:
            invoice = SubscriptionInvoice.objects.get(pk=pk)
        except SubscriptionInvoice.DoesNotExist:
            return Response({'detail': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)
        if invoice.pdf_url:
            return HttpResponseRedirect(invoice.pdf_url)
        return Response(
            {'detail': 'PDF not available for this invoice.'},
            status=status.HTTP_404_NOT_FOUND,
        )
