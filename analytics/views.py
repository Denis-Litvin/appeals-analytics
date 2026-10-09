from django.contrib.auth.decorators import permission_required
from django.shortcuts import render

analytics_required = permission_required("appeals.view_analytics", raise_exception=True)


# Все разделы пока заглушки, номер шага показывает, когда появится содержимое.
def _placeholder(request, title, step):
    return render(request, "placeholder.html", {"title": title, "step": step})


@analytics_required
def stats(request):
    return _placeholder(request, "Статистика", 11)


@analytics_required
def problems(request):
    return _placeholder(request, "Рейтинг проблем", 11)


@analytics_required
def compare(request):
    return _placeholder(request, "Сравнение периодов", 12)


@analytics_required
def dashboard(request):
    return _placeholder(request, "Дашборд", 14)


@analytics_required
def reports(request):
    return _placeholder(request, "Отчёты", 16)


@analytics_required
def alerts(request):
    return _placeholder(request, "Уведомления", 13)
