"""REST API (Д9). Числа берутся из тех же функций analytics/stats.py, что и страницы сайта,
фильтры из тех же форм, поэтому ответ API совпадает с тем, что аналитик видит в интерфейсе.
Права по ролям задаются словарём perms у каждой вьюхи (api/permissions.py)."""

from dataclasses import asdict

from django.utils.dateparse import parse_date
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics import stats
from analytics.forms import compare_form, period_form
from analytics.models import SpikeAlert
from analytics.spikes import check_appeal
from appeals.filters import filter_appeals
from appeals.models import Appeal
from appeals.views import ORDERINGS, ordering

from .serializers import AppealCreateSerializer, AppealSerializer, SpikeAlertSerializer

ANALYTICS = {"GET": "appeals.view_analytics"}
TOP_LIMIT = 50


def checked(form):
    """Форма с ошибкой в параметрах: ответ 400 с текстом ошибок. Сайт в таком случае молча берёт умолчания."""
    if form.errors:
        raise ValidationError({field: list(errors) for field, errors in form.errors.items()})
    return form


def period_info(start, end):
    return {"date_from": start, "date_to": end, "days": (end - start).days + 1}


def analytics_frame(request):
    form = checked(period_form(request.query_params))
    start, end = form.period
    return form, start, end, stats.load_frame(form.appeals())


class SummaryView(APIView):
    """Сводка за период: те же числа, что в плитках страницы «Статистика»."""

    perms = ANALYTICS

    def get(self, request):
        form, start, end, df = analytics_frame(request)
        return Response({"period": period_info(start, end), **asdict(stats.summary(df, start, end))})


class CategoriesView(APIView):
    perms = ANALYTICS

    def get(self, request):
        form, start, end, df = analytics_frame(request)
        rows = [
            {"name": r["name"], "slug": r["slug"], "count": r["count"], "share": r["share"]}
            for r in stats.by_category(df)
        ]
        return Response({"period": period_info(start, end), "total": len(df), "results": rows})


class TopReasonsView(APIView):
    perms = ANALYTICS

    def get(self, request):
        limit = request.query_params.get("limit", "10")
        if not limit.isdigit() or not 1 <= int(limit) <= TOP_LIMIT:
            raise ValidationError({"limit": [f"Целое число от 1 до {TOP_LIMIT}."]})
        form, start, end, df = analytics_frame(request)
        return Response({"period": period_info(start, end), "results": stats.top_reasons(df, int(limit))})


class ProblemsView(APIView):
    """Рейтинг причин (Д7) с предыдущим периодом той же длины."""

    perms = ANALYTICS

    def get(self, request):
        form, start, end, current = analytics_frame(request)
        prev_start, prev_end = stats.previous_period(start, end)
        previous = stats.load_frame(form.appeals(prev_start, prev_end))
        return Response(
            {
                "period": period_info(start, end),
                "previous_period": period_info(prev_start, prev_end),
                "results": stats.problems(current, previous),
            }
        )


class TimeseriesView(APIView):
    """Число обращений по дням: всего и по каждой категории."""

    perms = ANALYTICS

    def get(self, request):
        form, start, end, df = analytics_frame(request)
        table = stats.daily_table(df, start, end)
        series = [
            {"name": r["name"], "slug": r["slug"], "values": [int(v) for v in table[r["key"]]]}
            for r in stats.by_category(df)
        ]
        return Response(
            {
                "period": period_info(start, end),
                "days": list(table.index),
                "total": [int(v) for v in table.sum(axis=1)],
                "series": series,
            }
        )


class CompareView(APIView):
    """Сравнение периодов (Д6). Параметры как на странице: preset, base_from ... current_to, by."""

    perms = ANALYTICS

    def get(self, request):
        by = request.query_params.get("by", "category")
        if by not in ("category", "reason"):
            raise ValidationError({"by": ["category или reason."]})
        form = checked(compare_form(request.query_params))
        (base_from, base_to), (current_from, current_to) = form.base, form.current
        base_days = (base_to - base_from).days + 1
        current_days = (current_to - current_from).days + 1
        base = stats.load_frame(form.appeals(base_from, base_to))
        current = stats.load_frame(form.appeals(current_from, current_to))
        rows, totals = stats.compare(base, current, base_days, current_days, by=by)
        return Response(
            {
                "base_period": period_info(base_from, base_to),
                "current_period": period_info(current_from, current_to),
                "totals": totals,
                "results": rows,
            }
        )


class AlertListView(generics.ListAPIView):
    """Уведомления о резком росте (Д8). unread=1: только непрочитанные этим пользователем."""

    perms = ANALYTICS
    serializer_class = SpikeAlertSerializer

    def get_queryset(self):
        params = self.request.query_params
        alerts = SpikeAlert.objects.select_related("category", "reason")
        for name, lookup in (("date_from", "day__gte"), ("date_to", "day__lte")):
            if params.get(name):
                try:
                    day = parse_date(params[name])
                except ValueError:  # формат верный, но такой даты нет: 2026-13-01
                    day = None
                if day is None:
                    raise ValidationError({name: ["Дата в формате ГГГГ-ММ-ДД."]})
                alerts = alerts.filter(**{lookup: day})
        if params.get("unread") == "1":
            alerts = alerts.exclude(read_by=self.request.user)
        return alerts

    def get_serializer_context(self):
        read = SpikeAlert.read_by.through.objects.filter(user=self.request.user).values_list("spikealert_id", flat=True)
        return {**super().get_serializer_context(), "read_ids": set(read)}


class AppealListView(generics.ListCreateAPIView):
    """Список с фильтрами списка обращений (q, date_from, date_to, category, reason, tags, channel, status,
    source, assignee, order) и создание. Новое обращение получает категорию по словарю и проверяется на всплеск."""

    perms = {"GET": "appeals.view_appeal", "POST": "appeals.add_appeal"}

    def get_queryset(self):
        appeals, form = filter_appeals(self.request.query_params, self.request.user)
        checked(form)
        return (
            appeals.select_related("category", "reason", "assignee")
            .prefetch_related("tags")
            .order_by(*ORDERINGS[ordering(self.request.query_params)])
        )

    def get_serializer_class(self):
        return AppealCreateSerializer if self.request.method == "POST" else AppealSerializer

    def create(self, request, *args, **kwargs):
        serializer = AppealCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appeal = serializer.save()
        data = AppealSerializer(appeal, context=self.get_serializer_context()).data
        data["new_alerts"] = [str(alert) for alert in check_appeal(appeal)]
        return Response(data, status=201)


class AppealDetailView(generics.RetrieveAPIView):
    perms = {"GET": "appeals.view_appeal"}
    serializer_class = AppealSerializer
    queryset = Appeal.objects.select_related("category", "reason", "assignee").prefetch_related("tags")
