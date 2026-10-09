from django.shortcuts import render


def appeal_list(request):
    # Заглушка до шага 8.
    return render(request, "placeholder.html", {"title": "Обращения", "step": 8})
