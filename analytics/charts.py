"""Графики Plotly (О8, Д4). Фигуры строятся на сервере из тех же функций, что и таблицы в stats.py,
и уходят в шаблон как JSON. В customdata каждой точки лежит ссылка на список обращений этого среза:
клик по столбцу, сектору или точке открывает отфильтрованный список (static/js/charts.js)."""

import json
from functools import cache
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import plotly
import plotly.graph_objects as go
from django.urls import reverse
from plotly.offline import get_plotlyjs_version

from . import stats

PLOTLY_VERSION = get_plotlyjs_version()
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
ACCENT = "#2459a8"
GRID = "#eceef1"
TEXT = "#1f2328"
SPIKE = "#b42318"


@cache
def plotly_js():
    """Библиотека из пакета plotly: сервис работает без интернета и без CDN."""
    return PLOTLY_JS.read_bytes()


def figure(fig):
    """Фигура в обычный dict: numpy и даты превращаются в числа и строки."""
    return json.loads(fig.to_json())


def layout(**extra):
    base = {
        "template": "none",
        "margin": {"l": 48, "r": 16, "t": 8, "b": 40},
        "font": {"family": '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif', "size": 12, "color": TEXT},
        "separators": ", ",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "hoverlabel": {"bgcolor": "#ffffff", "font": {"color": TEXT}},
        "showlegend": False,
        "xaxis": {"gridcolor": GRID, "zeroline": False, "automargin": True},
        "yaxis": {"gridcolor": GRID, "zeroline": False, "automargin": True, "rangemode": "tozero"},
    }
    base.update(extra)
    return base


def list_link(base, **params):
    """Ссылка на список обращений: фильтры страницы плюс срез точки. Пустые значения не передаются."""
    query = {key: value for key, value in {**base, **params}.items() if value}
    return reverse("appeals:list") + "?" + urlencode(query)


def link_base(form):
    """Фильтры аналитической страницы в виде параметров списка обращений."""
    data = form.cleaned_data
    return {
        "date_from": data["date_from"].isoformat(),
        "date_to": data["date_to"].isoformat(),
        "category": data.get("category", ""),
        "channel": data.get("channel", ""),
    }


def daily(df, start, end, base, alerts=()):
    """Динамика по дням: линия на каждую категорию, треугольники в дни всплесков по категории."""
    days = pd.date_range(start, end, freq="D").date
    rows = stats.by_category(df)
    table = (
        df.assign(category=df["category"].fillna(stats.NO_CATEGORY))
        .groupby(["day", "category"]).size().unstack(fill_value=0)
        .reindex(index=days, fill_value=0)
    )
    fig = go.Figure()
    for row in rows:
        counts = table[row["key"]] if row["key"] in table else pd.Series(0, index=days)
        fig.add_trace(
            go.Scatter(
                x=[d.isoformat() for d in days],
                y=[int(v) for v in counts],
                name=row["name"],
                mode="lines",
                line={"color": row["color"], "width": 2},
                customdata=[list_link(base, category=row["slug"], date_from=d.isoformat(), date_to=d.isoformat())
                            for d in days],
                hovertemplate="%{x|%d.%m.%Y}<br>" + row["name"] + ": %{y}<extra></extra>",
            )
        )
    names = {row["key"]: row for row in rows}
    marks = [a for a in alerts if a.category.name in names and a.day in table.index]
    if marks:
        fig.add_trace(
            go.Scatter(
                x=[a.day.isoformat() for a in marks],
                y=[int(table.loc[a.day, a.category.name]) for a in marks],
                name="Всплеск",
                mode="markers",
                marker={"symbol": "triangle-up", "size": 12, "color": SPIKE, "line": {"color": "#ffffff", "width": 1}},
                text=[f"Всплеск: {a.category.name}, {a.count} при норме {a.baseline:g}" for a in marks],
                customdata=[list_link(base, category=a.category.slug, date_from=a.day.isoformat(),
                                      date_to=a.day.isoformat()) for a in marks],
                hovertemplate="%{x|%d.%m.%Y}<br>%{text}<extra></extra>",
            )
        )
    fig.update_layout(
        layout(
            showlegend=True,
            legend={"orientation": "h", "y": -0.15},
            hovermode="closest",
            xaxis={"gridcolor": GRID, "tickformat": "%d.%m", "automargin": True},
            margin={"l": 48, "r": 16, "t": 8, "b": 8},
        )
    )
    return figure(fig)


def categories(df, base):
    """Доли категорий, включая обращения без категории."""
    rows = stats.by_category(df)
    fig = go.Figure(
        go.Pie(
            labels=[r["name"] for r in rows],
            values=[r["count"] for r in rows],
            marker={"colors": [r["color"] for r in rows]},
            hole=0.45,
            sort=False,
            direction="clockwise",
            textinfo="percent",
            customdata=[list_link(base, category=r["slug"]) for r in rows],
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(layout(showlegend=True, legend={"x": 1, "y": 0.5}, margin={"l": 8, "r": 8, "t": 8, "b": 8}))
    return figure(fig)


def reasons(df, base, limit=10):
    """Топ причин горизонтальными столбцами, самая частая сверху."""
    rows = stats.top_reasons(df, limit)[::-1]
    fig = go.Figure(
        go.Bar(
            x=[r["count"] for r in rows],
            y=[r["name"] for r in rows],
            orientation="h",
            marker={"color": ACCENT},
            text=[r["category"] for r in rows],
            customdata=[list_link(base, reason=r["reason_id"]) for r in rows],
            hovertemplate="%{y}<br>%{text}<br>Обращений: %{x}<extra></extra>",
            textposition="none",
        )
    )
    fig.update_layout(layout(margin={"l": 8, "r": 16, "t": 8, "b": 32}))
    return figure(fig)


def heatmap(df):
    """День недели × час. Клик здесь ни к чему не ведёт: в списке нет фильтра по часу."""
    table = stats.weekday_hour(df)
    fig = go.Figure(
        go.Heatmap(
            z=[row["cells"] for row in table["rows"]],
            x=table["hours"],
            y=[row["weekday"] for row in table["rows"]],
            colorscale=[[0, "#ffffff"], [1, ACCENT]],
            xgap=1,
            ygap=1,
            hovertemplate="%{y}, %{x}:00<br>Обращений: %{z}<extra></extra>",
            colorbar={"thickness": 10, "outlinewidth": 0},
        )
    )
    fig.update_layout(
        layout(
            xaxis={"dtick": 1, "showgrid": False, "title": {"text": "час"}},
            yaxis={"autorange": "reversed", "showgrid": False},
            margin={"l": 40, "r": 8, "t": 8, "b": 40},
        )
    )
    return figure(fig)


def bars(rows, base, field):
    """Столбцы по каналам или статусам. field: параметр фильтра списка обращений."""
    fig = go.Figure(
        go.Bar(
            x=[r["name"] for r in rows],
            y=[r["count"] for r in rows],
            marker={"color": ACCENT},
            customdata=[list_link(base, **{field: r["key"]}) for r in rows],
            hovertemplate="%{x}: %{y}<extra></extra>",
        )
    )
    fig.update_layout(layout())
    return figure(fig)


def dashboard(df, form, alerts=()):
    start, end = form.period
    base = link_base(form)
    return {
        "daily": daily(df, start, end, base, alerts),
        "categories": categories(df, base),
        "reasons": reasons(df, base),
        "heatmap": heatmap(df),
        "channels": bars(stats.by_channel(df), base, "channel"),
        "statuses": bars(stats.by_status(df), base, "status"),
    }
