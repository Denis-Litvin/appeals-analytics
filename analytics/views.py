from django.contrib import messages
from django.contrib.auth.decorators import login_not_required, permission_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import charts, stats
from .forms import compare_form, period_form
from .models import SpikeAlert

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
    form = compare_form(request.GET)
    (base_from, base_to), (current_from, current_to) = form.base, form.current
    base_days = (base_to - base_from).days + 1
    current_days = (current_to - current_from).days + 1
    base = stats.load_frame(form.appeals(base_from, base_to))
    current = stats.load_frame(form.appeals(current_from, current_to))
    categories, totals = stats.compare(base, current, base_days, current_days, by="category")
    reasons, _ = stats.compare(base, current, base_days, current_days, by="reason")
    context = {
        "form": form,
        "base_from": base_from,
        "base_to": base_to,
        "current_from": current_from,
        "current_to": current_to,
        "base_days": base_days,
        "current_days": current_days,
        "totals": totals,
        "categories": categories,
        "reasons": reasons,
        "notable_share": stats.NOTABLE_SHARE,
        "notable_count": stats.NOTABLE_COUNT,
    }
    return render(request, "analytics/compare.html", context)


@analytics_required
def dashboard(request):
    form = period_form(request.GET)
    start, end = form.period
    df = stats.load_frame(form.appeals())
    context = {"form": form, "start": start, "end": end, "summary": stats.summary(df, start, end)}
    if len(df):
        alerts = SpikeAlert.objects.filter(reason__isnull=True, day__range=(start, end)).select_related("category")
        context["charts"] = charts.dashboard(df, form, alerts)
    return render(request, "analytics/dashboard.html", context)


@login_not_required
def plotly_js(request, version):
    """plotly.js из Python-пакета. Версия в адресе меняется вместе с пакетом, поэтому кэш можно держать год."""
    if version != charts.PLOTLY_VERSION:
        raise Http404
    response = HttpResponse(charts.plotly_js(), content_type="text/javascript; charset=utf-8")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@analytics_required
def reports(request):
    return _placeholder(request, "Отчёты", 16)


@analytics_required
def alerts(request):
    queryset = SpikeAlert.objects.select_related("category", "reason")
    unread_only = request.GET.get("unread") == "1"
    if unread_only:
        queryset = queryset.exclude(read_by=request.user)
    page = Paginator(queryset, 50).get_page(request.GET.get("page"))
    read_ids = set(
        SpikeAlert.read_by.through.objects.filter(user=request.user).values_list("spikealert_id", flat=True)
    )
    return render(request, "analytics/alerts.html", {"page": page, "read_ids": read_ids, "unread_only": unread_only})


@require_POST
@analytics_required
def alerts_read(request, pk=None):
    """Отметить прочитанным одно уведомление или все сразу."""
    alerts = SpikeAlert.objects.exclude(read_by=request.user)
    if pk is not None:
        alerts = alerts.filter(pk=pk)
    links = [
        SpikeAlert.read_by.through(spikealert_id=alert_id, user_id=request.user.pk)
        for alert_id in alerts.values_list("pk", flat=True)
    ]
    SpikeAlert.read_by.through.objects.bulk_create(links, ignore_conflicts=True)
    messages.success(request, f"Отмечено прочитанными: {len(links)}.")
    # Возврат только на свой сайт: адрес приходит из формы.
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "analytics:alerts"
    return redirect(next_url)
