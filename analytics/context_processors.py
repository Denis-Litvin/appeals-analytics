from .models import SpikeAlert


def alerts(request):
    """Число непрочитанных уведомлений для счётчика в меню. Считается только у тех, кто видит аналитику."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.has_perm("appeals.view_analytics"):
        return {}
    return {"unread_alerts": SpikeAlert.objects.exclude(read_by=user).count()}
