from rest_framework.permissions import BasePermission

# HEAD и OPTIONS только читают, им нужны те же права, что GET.
READ_METHODS = ("GET", "HEAD", "OPTIONS")


class RolePermission(BasePermission):
    """Права роли на метод запроса. Вьюха задаёт словарь perms: {"GET": "appeals.view_appeal", ...}.

    Метода нет в словаре: доступ закрыт. Анонима DRF отправит с 401, пользователя без права с 403.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        method = "GET" if request.method in READ_METHODS else request.method
        perm = getattr(view, "perms", {}).get(method)
        return bool(perm) and user.has_perm(perm)
