from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from customerapp.razorpay_service import RazorpayError

from ..eod_excel_report import build_transactions_workbook, render_workbook_bytes
from ..excel_report_addon_service import (
    create_excel_report_addon_order,
    excel_report_addon_status,
    has_excel_report_access,
    verify_excel_report_addon_payment,
)
from .seller_views import SellerAPIView


class ExcelReportAddonStatusView(SellerAPIView):
    def get(self, request):
        return Response(excel_report_addon_status(request.user))


class ExcelReportAddonCreateOrderView(SellerAPIView):
    def post(self, request):
        plan_slug = request.data.get('plan_slug') or request.data.get('plan')
        try:
            payload = create_excel_report_addon_order(seller=request.user, plan_slug=plan_slug)
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class ExcelReportAddonVerifyView(SellerAPIView):
    def post(self, request):
        data = request.data
        try:
            result = verify_excel_report_addon_payment(
                seller=request.user,
                razorpay_order_id=data.get('razorpay_order_id', ''),
                razorpay_payment_id=data.get('razorpay_payment_id', ''),
                razorpay_signature=data.get('razorpay_signature', ''),
            )
        except RazorpayError as exc:
            return Response(
                {'message': exc.message, 'code': exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)


class ExcelReportDownloadView(SellerAPIView):
    def get(self, request):
        seller = request.user
        if not has_excel_report_access(seller):
            return Response(
                {'message': 'Excel report addon not unlocked.', 'code': 'addon_locked'},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        wb = build_transactions_workbook(seller)
        content = render_workbook_bytes(wb)
        filename = f'excel-report-{timezone.localdate().isoformat()}.xlsx'

        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
