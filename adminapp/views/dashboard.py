from rest_framework.response import Response

from ..services.dashboard import (
    collections_chart,
    dashboard_stats,
    outstanding_by_status,
    recent_activity,
    signups_chart,
)
from ..utils import csv_response
from .base import AdminAPIView


class DashboardStatsView(AdminAPIView):
    def get(self, request):
        return Response(dashboard_stats())


class DashboardCollectionsChartView(AdminAPIView):
    def get(self, request):
        return Response(collections_chart(request.query_params.get('range', '30d')))


class DashboardSignupsChartView(AdminAPIView):
    def get(self, request):
        return Response(signups_chart(request.query_params.get('range', '30d')))


class DashboardOutstandingByStatusView(AdminAPIView):
    def get(self, request):
        return Response(outstanding_by_status())


class DashboardActivityView(AdminAPIView):
    def get(self, request):
        limit = int(request.query_params.get('limit', 20))
        return Response(recent_activity(limit=limit))


class DashboardExportView(AdminAPIView):
    def get(self, request):
        stats = dashboard_stats()
        rows = [[k, v] for k, v in stats.items()]
        return csv_response('dashboard-export.csv', rows, ['metric', 'value'])
