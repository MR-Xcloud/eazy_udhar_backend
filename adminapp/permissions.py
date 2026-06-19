from rest_framework.permissions import BasePermission

from .models import AdminUser


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, AdminUser)


class RoleRequired(BasePermission):
    """Require an admin user whose role is in the allowed list."""

    def __init__(self, allowed_roles):
        self.allowed_roles = set(allowed_roles)

    def has_permission(self, request, view):
        user = request.user
        if not isinstance(user, AdminUser):
            return False
        return user.role in self.allowed_roles
