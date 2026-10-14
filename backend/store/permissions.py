from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsVerifiedCustomer(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.email_verified
        )


class IsOwnerOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.can_manage_store or obj.user_id == request.user.id


class CanManageStore(BasePermission):
    message = "Solo el dueño o el superusuario puede gestionar la tienda."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.can_manage_store
        )
