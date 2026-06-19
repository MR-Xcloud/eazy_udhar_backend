import csv
from io import StringIO

from django.http import HttpResponse

from .models import AuditLog
from .pagination import AdminPagination


def admin_user_to_dict(user):
    return {
        'id': user.id,
        'email': user.email,
        'name': user.full_name,
        'role': user.role,
        'avatar_url': None,
    }


def mask_phone(phone):
    """Mask phone for display, e.g. +91 98••• ••342."""
    if not phone:
        return ''
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if len(digits) >= 10:
        last10 = digits[-10:]
        return f'+91 {last10[:2]}••• ••{last10[-3:]}'
    if len(digits) >= 4:
        return f'•••{digits[-4:]}'
    return '•••'


def mask_token(token):
    """Mask sensitive tokens (FCM, API keys) for display."""
    if not token:
        return ''
    text = str(token)
    if len(text) <= 8:
        return '•' * len(text)
    return f'{text[:4]}…{text[-4:]}'


def get_client_ip(request):
    if request is None:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit(admin, action, target_type, target_id, metadata=None, request=None):
    AuditLog.objects.create(
        admin=admin,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        metadata=metadata or {},
        ip_address=get_client_ip(request),
    )


def paginate_queryset(qs, request):
    paginator = AdminPagination()
    page = paginator.paginate_queryset(qs, request)
    return page, paginator


def csv_response(filename, rows, headers):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    response = HttpResponse(buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
