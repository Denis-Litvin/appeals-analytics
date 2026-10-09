"""Роли сотрудников, их права и маскирование персональных данных (Д10)."""

from django.contrib.auth.models import Group, Permission, User

OPERATOR = "Оператор"
ANALYST = "Аналитик"
ADMIN = "Администратор"

OPERATOR_PERMS = [
    "appeals.view_appeal",
    "appeals.add_appeal",
    "appeals.change_appeal",
    "appeals.view_personal_data",
    "appeals.view_category",
    "appeals.view_reason",
    "appeals.view_tag",
]

ANALYST_PERMS = [
    "appeals.view_appeal",
    "appeals.view_analytics",
    "appeals.export_reports",
    "appeals.view_category",
    "appeals.view_reason",
    "appeals.view_tag",
    "analytics.view_spikealert",
]

# Администратор получает всё, что есть у двух других ролей, плюс справочники и пользователей в админке.
ADMIN_PERMS = sorted(
    set(OPERATOR_PERMS)
    | set(ANALYST_PERMS)
    | {
        "appeals.manage_dictionary",
        "appeals.delete_appeal",
        "analytics.change_spikealert",
        "analytics.delete_spikealert",
        "auth.view_user",
        "auth.add_user",
        "auth.change_user",
        "auth.view_group",
    }
    | {
        f"appeals.{action}_{model}"
        for action in ("view", "add", "change", "delete")
        for model in ("category", "reason", "keywordrule", "tag")
    }
)

ROLES = {OPERATOR: OPERATOR_PERMS, ANALYST: ANALYST_PERMS, ADMIN: ADMIN_PERMS}

DEMO_PASSWORD = "demo12345"

# username, имя, фамилия, роль, доступ в админку
DEMO_USERS = [
    ("operator", "Ольга", "Смирнова", OPERATOR, False),
    ("operator2", "Дмитрий", "Орлов", OPERATOR, False),
    ("operator3", "Мария", "Ковалева", OPERATOR, False),
    ("analyst", "Артём", "Козлов", ANALYST, False),
    ("admin", "Игорь", "Белов", ADMIN, True),
]


def _permission(full_name):
    app_label, codename = full_name.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def setup_roles():
    """Создаёт группы ролей и выставляет им права. Повторный вызов приводит права к списку выше."""
    groups = {}
    for name, perms in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set([_permission(p) for p in perms])
        groups[name] = group
    return groups


def create_demo_users(groups):
    """Создаёт демо-учётки. Пароль выставляется только новым пользователям."""
    created = []
    for username, first_name, last_name, role, is_staff in DEMO_USERS:
        user, is_new = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first_name, "last_name": last_name, "email": f"{username}@example.com"},
        )
        if is_new:
            user.set_password(DEMO_PASSWORD)
            created.append(username)
        user.is_staff = is_staff
        user.save()
        user.groups.set([groups[role]])
    return created


def can_see_personal(user):
    return user.has_perm("appeals.view_personal_data")


def mask_email(email):
    if not email:
        return ""
    local, sep, domain = email.rpartition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def mask_name(name):
    return " ".join(f"{word[0]}***" for word in name.split())


def author_for(user, appeal):
    """Имя и email автора в том виде, в каком их можно показать этому пользователю."""
    if can_see_personal(user):
        return appeal.author_name, appeal.author_email
    return mask_name(appeal.author_name), mask_email(appeal.author_email)
