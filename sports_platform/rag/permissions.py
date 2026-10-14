"""
RAG Permissions — Milestone 9.
"""
from rest_framework.permissions import BasePermission


class IsDataAdminOrStaff(BasePermission):
    """
    Allows access only to staff members, superusers, or users with the 'data_admin' role.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        role = getattr(request.user, "role", "")
        return role == "data_admin"
