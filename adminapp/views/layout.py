from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from customerapp.models import Customer
from sellerapp.models import Seller, SellerCustomer

from ..models import AdminAlert
from .base import AdminAPIView


class GlobalSearchView(AdminAPIView):
    def get(self, request):
        q = (request.query_params.get('q') or '').strip()
        if not q:
            return Response({'sellers': [], 'customers': [], 'seller_customers': []})

        sellers = Seller.objects.filter(
            Q(business_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(full_name__icontains=q)
        )[:10]
        customers = Customer.objects.filter(
            Q(full_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(username__icontains=q)
        )[:10]
        seller_customers = SellerCustomer.objects.filter(
            Q(name__icontains=q) | Q(phone__icontains=q)
        ).select_related('seller')[:10]

        return Response(
            {
                'sellers': [
                    {
                        'id': s.id,
                        'business_name': s.business_name,
                        'phone': s.phone,
                    }
                    for s in sellers
                ],
                'customers': [
                    {
                        'id': c.id,
                        'full_name': c.full_name or c.username,
                        'phone': c.phone,
                    }
                    for c in customers
                ],
                'seller_customers': [
                    {
                        'id': str(sc.id),
                        'name': sc.name,
                        'phone': sc.phone,
                        'seller_id': sc.seller_id,
                    }
                    for sc in seller_customers
                ],
            }
        )


class AdminNotificationsView(AdminAPIView):
    def get(self, request):
        alerts = AdminAlert.objects.all().order_by('-created_at')[:50]
        unread_count = AdminAlert.objects.filter(read=False).count()
        return Response(
            {
                'unread_count': unread_count,
                'data': [
                    {
                        'id': a.id,
                        'type': a.type,
                        'title': a.title,
                        'body': a.body,
                        'link': a.link,
                        'created_at': a.created_at.isoformat(),
                        'read': a.read,
                    }
                    for a in alerts
                ],
            }
        )


class AdminNotificationDetailView(AdminAPIView):
    def patch(self, request, pk):
        try:
            alert = AdminAlert.objects.get(pk=pk)
        except AdminAlert.DoesNotExist:
            return Response({'detail': 'Notification not found.'}, status=status.HTTP_404_NOT_FOUND)
        if 'read' in request.data:
            alert.read = bool(request.data['read'])
            alert.save(update_fields=['read'])
        return Response(
            {
                'id': alert.id,
                'type': alert.type,
                'title': alert.title,
                'body': alert.body,
                'link': alert.link,
                'created_at': alert.created_at.isoformat(),
                'read': alert.read,
            }
        )


class AdminNotificationsMarkAllReadView(AdminAPIView):
    def post(self, request):
        AdminAlert.objects.filter(read=False).update(read=True)
        return Response({'detail': 'All notifications marked as read.'})
