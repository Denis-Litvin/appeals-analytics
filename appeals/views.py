from django.contrib.auth.decorators import permission_required
from django.shortcuts import render


@permission_required("appeals.view_appeal", raise_exception=True)
def appeal_list(request):
    # Заглушка до шага 8.
    return render(request, "placeholder.html", {"title": "Обращения", "step": 8})
