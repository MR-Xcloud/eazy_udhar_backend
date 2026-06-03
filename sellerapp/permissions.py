from rest_framework.permissions import BasePermission

from .models import Seller


class IsSeller(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, Seller)
