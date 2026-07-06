from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from ..models import AdminUser, AuditLog, CronJobStatus
from ..permissions import RoleRequired
from ..serializers import AdminUserSerializer
from ..services.password_reset import reset_user_password
from ..utils import log_audit
from .base import AdminAPIView

KNOWN_CRON_JOBS = ('run_auto_reminders', 'send_daily_summary', 'send_nightly_sms')


def _admin_list_item(user):
    return {
        'id': user.id,
        'email': user.email,
        'name': user.full_name,
        'role': user.role,
        'is_active': user.is_active,
        'last_login_at': user.last_login.isoformat() if user.last_login else None,
        'created_at': user.created_at.isoformat(),
    }


def _audit_item(entry):
    return {
        'id': entry.id,
        'admin_id': entry.admin_id,
        'admin_email': entry.admin.email if entry.admin_id else '',
        'action': entry.action,
        'target_type': entry.target_type,
        'target_id': entry.target_id,
        'metadata': entry.metadata,
        'ip_address': entry.ip_address,
        'created_at': entry.created_at.isoformat(),
    }


def _integration_status(name, configured):
    if configured:
        return {
            'name': name,
            'status': 'healthy',
            'last_checked_at': timezone.now().isoformat(),
        }
    return {
        'name': name,
        'status': 'not_configured',
        'last_checked_at': timezone.now().isoformat(),
        'message': 'Required credentials not configured.',
    }


class AdminUserListView(AdminAPIView):
    def get_permissions(self):
        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN])
        ]

    def get(self, request):
        qs = AdminUser.objects.all().order_by('-created_at')
        page, paginator = self.paginate(request, qs)
        data = [_admin_list_item(u) for u in page]
        return paginator.get_paginated_response(data)

    def post(self, request):
        serializer = AdminUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_audit(request.user, 'admin_create', 'admin', user.pk, request=request)
        return Response(_admin_list_item(user), status=status.HTTP_201_CREATED)


class AdminUserDetailView(AdminAPIView):
    def get_permissions(self):
        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN])
        ]

    def patch(self, request, pk):
        try:
            user = AdminUser.objects.get(pk=pk)
        except AdminUser.DoesNotExist:
            return Response({'detail': 'Admin not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminUserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_audit(request.user, 'admin_update', 'admin', user.pk, request=request)
        return Response(_admin_list_item(user))

    def delete(self, request, pk):
        try:
            user = AdminUser.objects.get(pk=pk)
        except AdminUser.DoesNotExist:
            return Response({'detail': 'Admin not found.'}, status=status.HTTP_404_NOT_FOUND)
        if user.pk == request.user.pk:
            return Response({'detail': 'Cannot deactivate your own account.'}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=['is_active'])
        log_audit(request.user, 'admin_deactivate', 'admin', user.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserResetPasswordView(AdminAPIView):
    def get_permissions(self):
        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, pk):
        try:
            user = AdminUser.objects.get(pk=pk)
        except AdminUser.DoesNotExist:
            return Response({'detail': 'Admin not found.'}, status=status.HTTP_404_NOT_FOUND)

        send_email = request.data.get('send_email', False)
        password = request.data.get('password')
        ok, payload = reset_user_password(
            user=user,
            account_type='admin',
            display_name=user.full_name or user.email,
            send_email=send_email,
            password=password,
        )
        if not ok:
            code = status.HTTP_400_BAD_REQUEST if payload.get('code') == 'invalid_password' else status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(payload, status=code)

        log_audit(request.user, 'admin_reset_password', 'admin', user.pk, request=request)
        return Response(payload)


class CronJobListView(AdminAPIView):
    def get(self, request):
        jobs = CronJobStatus.objects.all().order_by('name')
        if not jobs.exists():
            for name in KNOWN_CRON_JOBS:
                CronJobStatus.objects.get_or_create(
                    name=name,
                    defaults={'schedule': 'configured in crontab'},
                )
            jobs = CronJobStatus.objects.all().order_by('name')
        return Response(
            {
                'data': [
                    {
                        'name': job.name,
                        'schedule': job.schedule,
                        'last_run_at': job.last_run_at.isoformat() if job.last_run_at else None,
                        'last_status': job.last_status,
                        'last_error': job.last_error,
                        'next_run_at': job.next_run_at.isoformat() if job.next_run_at else None,
                    }
                    for job in jobs
                ]
            }
        )


class CronJobTriggerView(AdminAPIView):
    def get_permissions(self):
        return [perm() for perm in AdminAPIView.permission_classes] + [
            RoleRequired([AdminUser.ROLE_SUPER_ADMIN])
        ]

    def post(self, request, job):
        if job not in KNOWN_CRON_JOBS:
            return Response({'detail': f'Unknown job: {job}.'}, status=status.HTTP_400_BAD_REQUEST)
        cron, _ = CronJobStatus.objects.get_or_create(
            name=job,
            defaults={'schedule': 'manual'},
        )
        cron.last_status = CronJobStatus.LAST_STATUS_RUNNING
        cron.last_run_at = timezone.now()
        cron.save(update_fields=['last_status', 'last_run_at'])
        try:
            call_command(job)
            cron.last_status = CronJobStatus.LAST_STATUS_SUCCESS
            cron.last_error = ''
        except Exception as exc:
            cron.last_status = CronJobStatus.LAST_STATUS_FAILED
            cron.last_error = str(exc)[:2000]
        cron.save(update_fields=['last_status', 'last_error'])
        log_audit(request.user, 'cron_trigger', 'cron', job, request=request)
        return Response(
            {
                'name': cron.name,
                'last_status': cron.last_status,
                'last_error': cron.last_error,
                'last_run_at': cron.last_run_at.isoformat(),
            }
        )


def _fcm_integration_status():
    try:
        from easyudhar.fcm import fcm_health_status

        ok, message = fcm_health_status()
    except Exception as exc:
        return {
            'name': 'fcm',
            'status': 'not_configured',
            'last_checked_at': timezone.now().isoformat(),
            'message': str(exc),
        }
    if ok:
        return _integration_status('fcm', True)
    return {
        'name': 'fcm',
        'status': 'not_configured',
        'last_checked_at': timezone.now().isoformat(),
        'message': message or 'Required credentials not configured.',
    }


class SystemHealthView(AdminAPIView):
    def get(self, request):
        nimbus_ok = bool(
            getattr(settings, 'NIMBUS_SMS_ENABLED', False)
            and getattr(settings, 'NIMBUS_AUTH_KEY', '')
        )
        whatsapp_ok = bool(
            getattr(settings, 'WHATSAPP_API_ENABLED', False)
            and getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
            and getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
        )
        postmark_ok = bool(getattr(settings, 'POSTMARK_SERVER_TOKEN', ''))
        razorpay_ok = False
        try:
            from customerapp.razorpay_service import razorpay_configured

            razorpay_ok = razorpay_configured()
        except Exception:
            razorpay_ok = False

        return Response(
            {
                'integrations': [
                    _integration_status('nimbus_sms', nimbus_ok),
                    _integration_status('whatsapp', whatsapp_ok),
                    _fcm_integration_status(),
                    _integration_status('postmark', postmark_ok),
                    _integration_status('razorpay', razorpay_ok),
                ]
            }
        )


class AuditLogListView(AdminAPIView):
    def get(self, request):
        qs = AuditLog.objects.select_related('admin').order_by('-created_at')
        action = request.query_params.get('action')
        if action:
            qs = qs.filter(action=action)
        admin_id = request.query_params.get('admin_id')
        if admin_id:
            qs = qs.filter(admin_id=admin_id)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        page, paginator = self.paginate(request, qs)
        data = [_audit_item(e) for e in page]
        return paginator.get_paginated_response(data)
