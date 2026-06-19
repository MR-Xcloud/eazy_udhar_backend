from django.db.models import Q

from sellerapp.models import TeamMember

from ..services.data import team_member_item
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
