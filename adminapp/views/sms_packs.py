from decimal import Decimal, InvalidOperation

from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response

from ..models import SmsPack
from ..permissions import RoleRequired
from ..services.sms_packs import sms_pack_to_dict
from ..utils import log_audit
from .base import AdminAPIView


def _parse_decimal(value, *, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f'{field_name} must be a number.')


class SmsPackListView(AdminAPIView):
    def get(self, request):
        qs = SmsPack.objects.all().order_by('sort_order', 'sms_quantity')
        active_only = (request.query_params.get('active_only') or '').lower()
        if active_only in ('1', 'true', 'yes'):
            qs = qs.filter(is_active=True)
        return Response({'data': [sms_pack_to_dict(p) for p in qs]})

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
        if SmsPack.objects.filter(slug=slug).exists():
            return Response({'detail': 'Slug already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sms_quantity = int(request.data.get('sms_quantity'))
            unit_price_paise = _parse_decimal(
                request.data.get('unit_price_paise'), field_name='unit_price_paise'
            )
            gst_percent = _parse_decimal(
                request.data.get('gst_percent', 18), field_name='gst_percent'
            )
        except (TypeError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if sms_quantity <= 0:
            return Response({'detail': 'sms_quantity must be positive.'}, status=status.HTTP_400_BAD_REQUEST)
        if unit_price_paise <= 0:
            return Response(
                {'detail': 'unit_price_paise must be positive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pack = SmsPack.objects.create(
            name=name,
            slug=slug,
            sms_quantity=sms_quantity,
            unit_price_paise=unit_price_paise,
            gst_percent=gst_percent,
            is_active=request.data.get('is_active', True),
            sort_order=int(request.data.get('sort_order', 0) or 0),
        )
        log_audit(request.user, 'sms_pack_create', 'sms_pack', pack.pk, request=request)
        return Response(sms_pack_to_dict(pack), status=status.HTTP_201_CREATED)


class SmsPackDetailView(AdminAPIView):
    def get_permissions(self):
        from ..models import AdminUser

        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN, AdminUser.ROLE_FINANCE])
        ]

    def get(self, request, pk):
        try:
            pack = SmsPack.objects.get(pk=pk)
        except SmsPack.DoesNotExist:
            return Response({'detail': 'SMS pack not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(sms_pack_to_dict(pack))

    def patch(self, request, pk):
        try:
            pack = SmsPack.objects.get(pk=pk)
        except SmsPack.DoesNotExist:
            return Response({'detail': 'SMS pack not found.'}, status=status.HTTP_404_NOT_FOUND)

        if 'name' in request.data:
            pack.name = (request.data.get('name') or '').strip()
        if 'slug' in request.data:
            slug = (request.data.get('slug') or '').strip()
            if slug and SmsPack.objects.exclude(pk=pk).filter(slug=slug).exists():
                return Response({'detail': 'Slug already exists.'}, status=status.HTTP_400_BAD_REQUEST)
            pack.slug = slug
        if 'sms_quantity' in request.data:
            try:
                sms_quantity = int(request.data['sms_quantity'])
            except (TypeError, ValueError):
                return Response({'detail': 'Invalid sms_quantity.'}, status=status.HTTP_400_BAD_REQUEST)
            if sms_quantity <= 0:
                return Response({'detail': 'sms_quantity must be positive.'}, status=status.HTTP_400_BAD_REQUEST)
            pack.sms_quantity = sms_quantity
        for field in ('unit_price_paise', 'gst_percent'):
            if field in request.data:
                try:
                    value = _parse_decimal(request.data[field], field_name=field)
                except ValueError as exc:
                    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
                if field == 'unit_price_paise' and value <= 0:
                    return Response(
                        {'detail': 'unit_price_paise must be positive.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(pack, field, value)
        if 'is_active' in request.data:
            pack.is_active = bool(request.data['is_active'])
        if 'sort_order' in request.data:
            pack.sort_order = int(request.data.get('sort_order') or 0)

        pack.save()
        log_audit(request.user, 'sms_pack_update', 'sms_pack', pack.pk, request=request)
        return Response(sms_pack_to_dict(pack))

    def delete(self, request, pk):
        try:
            pack = SmsPack.objects.get(pk=pk)
        except SmsPack.DoesNotExist:
            return Response({'detail': 'SMS pack not found.'}, status=status.HTTP_404_NOT_FOUND)
        pack.is_active = False
        pack.save(update_fields=['is_active', 'updated_at'])
        log_audit(request.user, 'sms_pack_deactivate', 'sms_pack', pack.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
