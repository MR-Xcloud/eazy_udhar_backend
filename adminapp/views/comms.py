from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from customerapp.models import OTPRecord
from sellerapp.models import ReminderLog, SellerSettings
from sellerapp.reminders import send_customer_reminder

from ..services.data import reminder_log_item
from ..utils import log_audit
from .base import AdminAPIView


def _filter_reminder_logs(request):
    qs = ReminderLog.objects.select_related('seller', 'customer').order_by('-sent_at')
    channel = request.query_params.get('channel')
    if channel:
        qs = qs.filter(channel=channel)
    reminder_type = request.query_params.get('type')
    if reminder_type:
        qs = qs.filter(reminder_type=reminder_type)
    status_param = request.query_params.get('status')
    if status_param == 'sent':
        qs = qs.filter(success=True)
    elif status_param == 'failed':
        qs = qs.filter(success=False)
    seller_id = request.query_params.get('seller_id')
    if seller_id:
        qs = qs.filter(seller_id=seller_id)
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    if date_from:
        qs = qs.filter(sent_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(sent_at__date__lte=date_to)
    return qs


def _otp_status(record):
    if record.is_verified:
        return 'verified'
    if record.expires_at < timezone.now():
        return 'expired'
    return 'sent'


def _otp_item(record):
    contact = record.phone or record.email or ''
    return {
        'id': str(record.id),
        'phone': contact,
        'recipient': contact,
        'purpose': record.purpose,
        'status': _otp_status(record),
        'attempts': 1,
        'ip_address': None,
        'created_at': record.created_at.isoformat(),
        'verified_at': record.created_at.isoformat() if record.is_verified else None,
    }


class ReminderLogListView(AdminAPIView):
    def get(self, request):
        qs = _filter_reminder_logs(request)
        page, paginator = self.paginate(request, qs)
        data = [reminder_log_item(log) for log in page]
        return paginator.get_paginated_response(data)


class ReminderLogResendView(AdminAPIView):
    def post(self, request, pk):
        try:
            log = ReminderLog.objects.select_related('seller', 'customer').get(pk=pk)
        except ReminderLog.DoesNotExist:
            return Response({'detail': 'Reminder log not found.'}, status=status.HTTP_404_NOT_FOUND)
        if log.success:
            return Response({'detail': 'Only failed reminders can be resent.'}, status=status.HTTP_400_BAD_REQUEST)

        settings, _ = SellerSettings.objects.get_or_create(seller=log.seller)
        channels = settings.reminder_channels or [log.channel]
        if log.channel not in channels:
            channels = [log.channel]

        results = send_customer_reminder(
            log.seller,
            log.customer,
            channels=channels,
            reminder_type=log.reminder_type,
        )
        log_audit(request.user, 'reminder_resend', 'reminder_log', log.pk, request=request)
        return Response({'detail': 'Reminder resent.', 'results': results})


class OTPRecordListView(AdminAPIView):
    def get(self, request):
        qs = OTPRecord.objects.all().order_by('-created_at')
        phone = (request.query_params.get('phone') or '').strip()
        if phone:
            qs = qs.filter(phone__icontains=phone)
        purpose = request.query_params.get('purpose')
        if purpose:
            qs = qs.filter(purpose=purpose)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        page, paginator = self.paginate(request, qs)
        data = [_otp_item(r) for r in page]
        return paginator.get_paginated_response(data)
