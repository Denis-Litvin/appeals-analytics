from django.shortcuts import render


# Все разделы пока заглушки, номер шага показывает, когда появится содержимое.
def _placeholder(request, title, step):
    return render(request, "placeholder.html", {"title": title, "step": step})


def stats(request):
    return _placeholder(request, "Статистика", 11)


def problems(request):
    return _placeholder(request, "Рейтинг проблем", 11)


def compare(request):
    return _placeholder(request, "Сравнение периодов", 12)


def dashboard(request):
    return _placeholder(request, "Дашборд", 14)


def reports(request):
    return _placeholder(request, "Отчёты", 16)


def alerts(request):
    return _placeholder(request, "Уведомления", 13)
