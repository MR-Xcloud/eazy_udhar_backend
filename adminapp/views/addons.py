"""Admin API for the Excel-report add-on: plan management + purchase history.

The plans here are what the seller app offers at checkout; the orders are the
resulting purchases, each of which raises an invoice that syncs to CRM finance
exactly like a subscription invoice does.
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response

from sellerapp.models import SellerExcelReportOrder, SellerSettings

from ..models import ExcelReportAddonPlan, SubscriptionInvoice
from ..permissions import RoleRequired
from ..services.addon_invoices import issue_addon_invoice
from ..services.download_tokens import make_invoice_download_token
from ..utils import log_audit
from .base import AdminAPIView


def _parse_decimal(value, *, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f'{field_name} must be a number.')


def plan_to_dict(plan):
    return {
        'id': plan.id,
        'name': plan.name,
        'slug': plan.slug,
        'duration_days': plan.duration_days,
        'price_inr': float(plan.price_inr),
        'gst_percent': float(plan.gst_percent),
        'gst_amount_inr': float(plan.gst_amount),
        'total_inr': float(plan.total_inr),
        'is_active': plan.is_active,
        'sort_order': plan.sort_order,
        'created_at': plan.created_at.isoformat(),
        'updated_at': plan.updated_at.isoformat(),
    }


ADMIN_API_BASE = f"{(getattr(django_settings, 'PUBLIC_STATEMENT_BASE_URL', '') or '').rstrip('/')}/admin-api/v1"


def _access_for(order, invoice, *, expiry_by_seller, latest_order_id_by_seller, now):
    """Access this purchase bought, folded onto the order row.

    Add-on access is a single expiry stamp per seller that top-ups *stack*
    onto, so only the seller's most recent paid order owns the current window —
    earlier ones were superseded by a renewal and get no live end date.
    """
    is_current = latest_order_id_by_seller.get(order.seller_id) == order.id
    expires_at = expiry_by_seller.get(order.seller_id) if is_current else None
    if order.status != SellerExcelReportOrder.STATUS_PAID:
        access_state = 'none'
    elif not is_current:
        access_state = 'superseded'
    elif expires_at and expires_at > now:
        access_state = 'active'
    else:
        access_state = 'expired'

    if invoice is not None and invoice.payment_method == SubscriptionInvoice.PAYMENT_METHOD_OFFLINE:
        payment_mode = invoice.get_payment_method_display()
        payment_reference = invoice.offline_reference or None
    elif order.status == SellerExcelReportOrder.STATUS_PAID:
        payment_mode = 'Razorpay'
        payment_reference = order.razorpay_payment_id or None
    else:
        payment_mode = None
        payment_reference = None

    return {
        'access_state': access_state,
        'access_start_at': (order.paid_at or order.created_at).isoformat()
        if order.status == SellerExcelReportOrder.STATUS_PAID else None,
        'access_end_at': expires_at.isoformat() if expires_at else None,
        'days_remaining': max((expires_at - now).days, 0)
        if access_state == 'active' and expires_at else None,
        'payment_mode': payment_mode,
        'payment_reference': payment_reference,
        'invoice_download_url': (
            f'{ADMIN_API_BASE}/subscriptions/invoices/{invoice.id}/download'
            f'?token={make_invoice_download_token(invoice.id)}'
        ) if invoice else None,
        'invoice_status': invoice.status if invoice else None,
    }


def order_to_dict(order, *, expiry_by_seller=None, latest_order_id_by_seller=None, now=None):
    invoice = order.invoices.first()
    access = _access_for(
        order,
        invoice,
        expiry_by_seller=expiry_by_seller or {},
        latest_order_id_by_seller=latest_order_id_by_seller or {},
        now=now or timezone.now(),
    ) if expiry_by_seller is not None else {}
    return {
        **access,
        'id': str(order.id),
        'reference_id': order.reference_id,
        'seller_id': order.seller_id,
        'seller_name': order.seller.business_name,
        'seller_email': order.seller.email,
        'plan_slug': order.plan_slug,
        'plan_name': order.plan_name,
        'duration_days': order.duration_days,
        'amount': float(order.amount),
        'currency': order.currency,
        'status': order.status,
        'razorpay_order_id': order.razorpay_order_id,
        'razorpay_payment_id': order.razorpay_payment_id or None,
        'error_message': order.error_message or None,
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
        'created_at': order.created_at.isoformat(),
        'invoice_number': invoice.display_number if invoice else None,
        'invoice_id': invoice.id if invoice else None,
        'crm_sync_status': invoice.crm_sync_status if invoice else None,
    }


class ExcelAddonPlanListView(AdminAPIView):
    def get(self, request):
        qs = ExcelReportAddonPlan.objects.all()
        active_only = (request.query_params.get('active_only') or '').lower()
        if active_only in ('1', 'true', 'yes'):
            qs = qs.filter(is_active=True)
        return Response({'data': [plan_to_dict(p) for p in qs]})

    def get_permissions(self):
        from ..models import AdminUser

        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method == 'POST':
            perms.append(RoleRequired([AdminUser.ROLE_SUPER_ADMIN, AdminUser.ROLE_FINANCE]))
        return perms

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        slug = (request.data.get('slug') or '').strip() or slugify(name)
        if not name:
            return Response({'detail': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not slug:
            return Response({'detail': 'Slug is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if ExcelReportAddonPlan.objects.filter(slug=slug).exists():
            return Response({'detail': 'Slug already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            duration_days = int(request.data.get('duration_days'))
            price_inr = _parse_decimal(request.data.get('price_inr'), field_name='price_inr')
            gst_percent = _parse_decimal(
                request.data.get('gst_percent', 18), field_name='gst_percent'
            )
        except (TypeError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if duration_days <= 0:
            return Response(
                {'detail': 'duration_days must be positive.'}, status=status.HTTP_400_BAD_REQUEST
            )
        if price_inr <= 0:
            return Response(
                {'detail': 'price_inr must be positive.'}, status=status.HTTP_400_BAD_REQUEST
            )

        plan = ExcelReportAddonPlan.objects.create(
            name=name,
            slug=slug,
            duration_days=duration_days,
            price_inr=price_inr,
            gst_percent=gst_percent,
            is_active=bool(request.data.get('is_active', True)),
            sort_order=int(request.data.get('sort_order') or 0),
        )
        log_audit(
            request.user, 'excel_addon_plan_create', 'excel_addon_plan', plan.pk, request=request
        )
        return Response(plan_to_dict(plan), status=status.HTTP_201_CREATED)


class ExcelAddonPlanDetailView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN, AdminUser.ROLE_FINANCE])
        ]

    def _get(self, pk):
        try:
            return ExcelReportAddonPlan.objects.get(pk=pk)
        except ExcelReportAddonPlan.DoesNotExist:
            return None

    def get(self, request, pk):
        plan = self._get(pk)
        if plan is None:
            return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(plan_to_dict(plan))

    def patch(self, request, pk):
        plan = self._get(pk)
        if plan is None:
            return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)

        if 'name' in request.data:
            name = (request.data.get('name') or '').strip()
            if not name:
                return Response({'detail': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)
            plan.name = name
        if 'slug' in request.data:
            slug = (request.data.get('slug') or '').strip()
            if not slug:
                return Response({'detail': 'Slug is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if ExcelReportAddonPlan.objects.exclude(pk=pk).filter(slug=slug).exists():
                return Response(
                    {'detail': 'Slug already exists.'}, status=status.HTTP_400_BAD_REQUEST
                )
            plan.slug = slug
        if 'duration_days' in request.data:
            try:
                duration_days = int(request.data['duration_days'])
            except (TypeError, ValueError):
                return Response(
                    {'detail': 'Invalid duration_days.'}, status=status.HTTP_400_BAD_REQUEST
                )
            if duration_days <= 0:
                return Response(
                    {'detail': 'duration_days must be positive.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            plan.duration_days = duration_days
        for field in ('price_inr', 'gst_percent'):
            if field in request.data:
                try:
                    value = _parse_decimal(request.data[field], field_name=field)
                except ValueError as exc:
                    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
                if field == 'price_inr' and value <= 0:
                    return Response(
                        {'detail': 'price_inr must be positive.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(plan, field, value)
        if 'is_active' in request.data:
            plan.is_active = bool(request.data['is_active'])
        if 'sort_order' in request.data:
            plan.sort_order = int(request.data.get('sort_order') or 0)

        plan.save()
        log_audit(
            request.user, 'excel_addon_plan_update', 'excel_addon_plan', plan.pk, request=request
        )
        return Response(plan_to_dict(plan))

    def delete(self, request, pk):
        plan = self._get(pk)
        if plan is None:
            return Response({'detail': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Orders freeze the plan name and price at purchase, so removing a tier
        # never rewrites history — but deactivating keeps the audit trail
        # readable, which is why the UI offers that first.
        log_audit(
            request.user, 'excel_addon_plan_delete', 'excel_addon_plan', plan.pk,
            {'slug': plan.slug}, request,
        )
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExcelAddonOrderListView(AdminAPIView):
    """Purchases and the access each one bought, in one list — a purchase row
    is only half the story without the window it granted."""

    def get(self, request):
        now = timezone.now()
        qs = (
            SellerExcelReportOrder.objects
            .select_related('seller')
            .prefetch_related('invoices')
            .order_by('-created_at')
        )
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        order_status = request.query_params.get('status')
        if order_status:
            qs = qs.filter(status=order_status)
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(seller__business_name__icontains=search)
                | Q(seller__email__icontains=search)
                | Q(seller__phone__icontains=search)
                | Q(plan_name__icontains=search)
                | Q(reference_id__icontains=search)
                | Q(razorpay_order_id__icontains=search)
                | Q(razorpay_payment_id__icontains=search)
            )
        # "Access" is per seller, not per order, so filter to the sellers whose
        # entitlement is still live and let the row builder mark which of their
        # orders actually owns that window.
        if (request.query_params.get('access') or '').lower() == 'active':
            qs = qs.filter(
                status=SellerExcelReportOrder.STATUS_PAID,
                seller__settings__excel_report_addon_expires_at__gt=now,
            )

        page, paginator = self.paginate(request, qs)
        seller_ids = {o.seller_id for o in page}
        expiry_by_seller = dict(
            SellerSettings.objects
            .filter(seller_id__in=seller_ids)
            .values_list('seller_id', 'excel_report_addon_expires_at')
        )
        # Picked in Python: the pk is a UUID, so MAX(id) is not "the newest",
        # and paid_at can be null on legacy rows.
        latest_order_id_by_seller = {}
        paid_orders = SellerExcelReportOrder.objects.filter(
            seller_id__in=seller_ids, status=SellerExcelReportOrder.STATUS_PAID
        ).only('id', 'seller_id', 'paid_at', 'created_at')
        for o in sorted(paid_orders, key=lambda o: (o.paid_at or o.created_at), reverse=True):
            latest_order_id_by_seller.setdefault(o.seller_id, o.id)
        data = [
            order_to_dict(
                o,
                expiry_by_seller=expiry_by_seller,
                latest_order_id_by_seller=latest_order_id_by_seller,
                now=now,
            )
            for o in page
        ]
        return paginator.get_paginated_response(data)


class ExcelAddonOrderInvoiceView(AdminAPIView):
    """Raise the invoice for a paid order that never got one — an order paid
    before invoicing existed, or one whose invoice creation failed."""

    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN, AdminUser.ROLE_FINANCE])
        ]

    def post(self, request, pk):
        try:
            order = SellerExcelReportOrder.objects.select_related('seller').get(pk=pk)
        except (SellerExcelReportOrder.DoesNotExist, ValueError):
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if order.status != SellerExcelReportOrder.STATUS_PAID:
            return Response(
                {'detail': 'Only paid orders can be invoiced.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = SubscriptionInvoice.objects.filter(addon_order=order).first()
        invoice = existing or issue_addon_invoice(order)
        if invoice is None:
            return Response(
                {'detail': 'Could not raise the invoice — see the server log.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        log_audit(
            request.user, 'excel_addon_invoice_issue', 'invoice', invoice.pk,
            {'order': order.reference_id}, request,
        )
        return Response(order_to_dict(order))
