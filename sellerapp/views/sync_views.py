import logging

from rest_framework import status
from rest_framework.response import Response

from ..serializers import SyncPushSerializer
from ..sync_service import SyncError, pull_changes, push_sync
from .seller_views import SellerAPIView

logger = logging.getLogger(__name__)


class SellerSyncPushView(SellerAPIView):
    def post(self, request):
        serializer = SyncPushSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning('sync/push validation failed: %s body=%s', serializer.errors, request.data)
            serializer.is_valid(raise_exception=True)
        try:
            result = push_sync(request.user, serializer.validated_data['operations'])
        except SyncError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.status_code,
            )
        return Response(result, status=status.HTTP_200_OK)


class SellerSyncChangesView(SellerAPIView):
    def get(self, request):
        since = request.query_params.get('since', '')
        try:
            data = pull_changes(request.user, since=since or None)
        except SyncError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=exc.status_code,
            )
        return Response(data, status=status.HTTP_200_OK)
