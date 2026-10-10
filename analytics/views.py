from django.contrib.auth.decorators import permission_required
from django.shortcuts import render

from . import stats
from .forms import period_form

analytics_required = permission_required("appeals.view_analytics", raise_exception=True)


# Разделы, которые ещё не готовы, номер шага показывает, когда появится содержимое.
def _placeholder(request, title, step):
    return render(request, "placeholder.html", {"title": title, "step": step})


@analytics_required
def stats_page(request):
    form = period_form(request.GET)
    start, end = form.period
    df = stats.load_frame(form.appeals())
    context = {"form": form, "start": start, "end": end, "summary": stats.summary(df, start, end)}
    if len(df):
        context.update(
            categories=stats.by_category(df),
            channels=stats.by_channel(df),
            statuses=stats.by_status(df),
            reasons=stats.top_reasons(df),
            heatmap=stats.weekday_hour(df),
        )
    return render(request, "analytics/stats.html", context)


@analytics_required
def problems(request):
    form = period_form(request.GET)
    start, end = form.period
    prev_start, prev_end = stats.previous_period(start, end)
    current = stats.load_frame(form.appeals())
    previous = stats.load_frame(form.appeals(prev_start, prev_end))
    context = {
        "form": form,
        "start": start,
        "end": end,
        "prev_start": prev_start,
        "prev_end": prev_end,
        "rows": stats.problems(current, previous),
        "total": len(current),
    }
    return render(request, "analytics/problems.html", context)


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
