from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from ..models import PromoCode, PromoRedemption
from ..utils import log_audit
from .base import AdminAPIView


def _promo_item(promo):
    return {
        'id': promo.id,
        'code': promo.code,
        'discount_type': promo.discount_type,
        'discount_value': float(promo.discount_value),
        'max_uses': promo.max_uses,
        'uses_count': promo.uses_count,
        'valid_from': promo.valid_from.isoformat(),
        'valid_until': promo.valid_until.isoformat(),
        'is_active': promo.is_active,
        'created_at': promo.created_at.isoformat(),
    }


def _redemption_item(redemption):
    return {
        'id': redemption.id,
        'promo_code': redemption.promo.code,
        'customer_id': redemption.customer_id,
        'customer_name': redemption.customer_name,
        'seller_id': redemption.seller_id,
        'redeemed_at': redemption.redeemed_at.isoformat(),
    }


class PromoCodeListView(AdminAPIView):
    def get(self, request):
        qs = PromoCode.objects.all().order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [_promo_item(p) for p in page]
        return paginator.get_paginated_response(data)

    def post(self, request):
        code = (request.data.get('code') or '').strip().upper()
        if not code:
            return Response({'detail': 'Code is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if PromoCode.objects.filter(code=code).exists():
            return Response({'detail': 'Code already exists.'}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        promo = PromoCode.objects.create(
            code=code,
            discount_type=request.data.get('discount_type', PromoCode.DISCOUNT_PERCENT),
            discount_value=request.data.get('discount_value', 0),
            max_uses=request.data.get('max_uses'),
            valid_from=request.data.get('valid_from', now),
            valid_until=request.data.get('valid_until', now),
            is_active=request.data.get('is_active', True),
        )
        log_audit(request.user, 'promo_create', 'promo_code', promo.pk, request=request)
        return Response(_promo_item(promo), status=status.HTTP_201_CREATED)


class PromoCodeDetailView(AdminAPIView):
    def patch(self, request, pk):
        try:
            promo = PromoCode.objects.get(pk=pk)
        except PromoCode.DoesNotExist:
            return Response({'detail': 'Promo code not found.'}, status=status.HTTP_404_NOT_FOUND)
        for field in (
            'code',
            'discount_type',
            'discount_value',
            'max_uses',
            'valid_from',
            'valid_until',
            'is_active',
        ):
            if field in request.data:
                setattr(promo, field, request.data[field])
        promo.save()
        log_audit(request.user, 'promo_update', 'promo_code', promo.pk, request=request)
        return Response(_promo_item(promo))

    def delete(self, request, pk):
        try:
            promo = PromoCode.objects.get(pk=pk)
        except PromoCode.DoesNotExist:
            return Response({'detail': 'Promo code not found.'}, status=status.HTTP_404_NOT_FOUND)
        promo.is_active = False
        promo.save(update_fields=['is_active'])
        log_audit(request.user, 'promo_deactivate', 'promo_code', promo.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PromoRedemptionListView(AdminAPIView):
    def get(self, request):
        qs = PromoRedemption.objects.select_related('promo').order_by('-redeemed_at')
        promo_code = (request.query_params.get('promo_code') or '').strip()
        if promo_code:
            qs = qs.filter(promo__code__iexact=promo_code)
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(redeemed_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(redeemed_at__date__lte=date_to)
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(customer_name__icontains=search) | Q(promo__code__icontains=search)
            )
        page, paginator = self.paginate(request, qs)
        data = [_redemption_item(r) for r in page]
        return paginator.get_paginated_response(data)
