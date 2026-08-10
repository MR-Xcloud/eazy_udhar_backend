from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from sellerapp.models import TeamMember

from ..models import AdminUser
from ..permissions import RoleRequired
from ..services.data import team_member_item
from ..utils import log_audit
from .base import AdminAPIView


class TeamMembersListView(AdminAPIView):
    def get(self, request):
        qs = TeamMember.objects.select_related('seller').order_by('-created_at')
        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(seller__business_name__icontains=search)
            )
        seller_id = request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        page, paginator = self.paginate(request, qs)
        data = [team_member_item(m) for m in page]
        return paginator.get_paginated_response(data)


class TeamMemberUpdateView(AdminAPIView):
    def get_permissions(self):
        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPPORT, AdminUser.ROLE_SUPER_ADMIN])
        ]

    def patch(self, request, pk, member_id):
        try:
            member = TeamMember.objects.select_related('seller').get(pk=member_id, seller_id=pk)
        except TeamMember.DoesNotExist:
            return Response({'detail': 'Team member not found.'}, status=status.HTTP_404_NOT_FOUND)

        status_value = request.data.get('status')
        if status_value not in ('active', 'inactive'):
            return Response({'detail': 'status must be "active" or "inactive".'}, status=status.HTTP_400_BAD_REQUEST)

        member.is_active = status_value == 'active'
        member.save(update_fields=['is_active'])
        log_audit(
            request.user,
            'team_member_deactivate' if not member.is_active else 'team_member_reactivate',
            'team_member',
            member.pk,
            {'seller_id': member.seller_id},
            request=request,
        )
        return Response(team_member_item(member))
