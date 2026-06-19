from rest_framework.views import APIView

from ..authentication import AdminJWTAuthentication
from ..pagination import AdminPagination
from ..permissions import IsAdminUser


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    pagination_class = AdminPagination

    def paginate(self, request, queryset):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        return page, paginator
