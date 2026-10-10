"""Статистика по обращениям (О6, О7, Д7). Выборка загружается в pandas одним запросом, дальше всё в памяти."""

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from appeals.models import Appeal

TZ = "Europe/Moscow"
NO_CATEGORY = "Без категории"
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
OPEN_STATUSES = (Appeal.Status.NEW, Appeal.Status.IN_WORK)
CHANNELS = dict(Appeal.Channel.choices)
STATUSES = dict(Appeal.Status.choices)
COLUMNS = [
    "id", "created_at", "resolved_at", "channel", "status", "category_source",
    "category_id", "category__name", "category__slug", "category__color", "reason_id", "reason__name",
]


def load_frame(queryset):
    """Обращения в DataFrame: время по Москве, часы решения, удобные имена колонок."""
    rows = list(queryset.values_list(*COLUMNS))
    df = pd.DataFrame(rows, columns=COLUMNS).rename(
        columns={
            "category__name": "category",
            "category__slug": "category_slug",
            "category__color": "color",
            "reason__name": "reason",
        }
    )
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert(TZ)
    df["resolved_at"] = pd.to_datetime(df["resolved_at"], utc=True).dt.tz_convert(TZ)
    df["day"] = df["created_at"].dt.date
    df["weekday"] = df["created_at"].dt.weekday
    df["hour"] = df["created_at"].dt.hour
    df["hours_to_resolve"] = (df["resolved_at"] - df["created_at"]).dt.total_seconds() / 3600
    df["is_open"] = df["status"].isin(OPEN_STATUSES)
    return df


def median_hours(series):
    series = series.dropna()
    return round(float(series.median()), 1) if len(series) else None


@dataclass
class Summary:
    total: int
    days: int
    per_day: float
    open_count: int
    open_share: float
    without_category: int
    without_category_share: float
    manual_share: float
    median_resolution_hours: float | None


def summary(df, start, end):
    days = (end - start).days + 1
    total = len(df)
    share = (lambda n: n / total) if total else (lambda n: 0.0)
    without = int(df["category_id"].isna().sum())
    open_count = int(df["is_open"].sum())
    return Summary(
        total=total,
        days=days,
        per_day=round(total / days, 1),
        open_count=open_count,
        open_share=share(open_count),
        without_category=without,
        without_category_share=share(without),
        manual_share=share(int((df["category_source"] == Appeal.Source.MANUAL).sum())),
        median_resolution_hours=median_hours(df["hours_to_resolve"]),
    )


def breakdown(df, column, labels=None):
    """Количество и доля по значениям колонки, по убыванию. Пустые значения считаются отдельной строкой."""
    total = len(df)
    counts = df[column].fillna(NO_CATEGORY).value_counts()
    return [
        {"name": (labels or {}).get(key, key), "key": key, "count": int(n), "share": n / total}
        for key, n in counts.items()
    ]


def by_category(df):
    rows = breakdown(df, "category")
    colors = dict(zip(df["category"], df["color"]))
    slugs = dict(zip(df["category"], df["category_slug"]))
    for row in rows:
        row["color"] = colors.get(row["key"], "#b42318")
        row["slug"] = slugs.get(row["key"], "none")
    return rows


def by_channel(df):
    return breakdown(df, "channel", CHANNELS)


def by_status(df):
    return breakdown(df, "status", STATUSES)


def top_reasons(df, limit=10):
    """Самые частые причины. Доля считается от всех обращений периода, включая непонятные."""
    total = len(df)
    known = df.dropna(subset=["reason_id"])
    grouped = known.groupby(["reason_id", "reason", "category"]).size().sort_values(ascending=False).head(limit)
    return [
        {"reason_id": int(rid), "name": name, "category": category, "count": int(n), "share": n / total}
        for (rid, name, category), n in grouped.items()
    ]


def weekday_hour(df):
    """Таблица день недели × час: количество обращений в каждой клетке."""
    table = pd.crosstab(df["weekday"], df["hour"]).reindex(index=range(7), columns=range(24), fill_value=0)
    peak = int(table.values.max()) if len(df) else 0
    return {
        "rows": [
            {"weekday": WEEKDAYS[wd], "cells": [int(v) for v in table.loc[wd]], "total": int(table.loc[wd].sum())}
            for wd in range(7)
        ],
        "hours": list(range(24)),
        "peak": peak,
    }


def previous_period(start, end):
    """Предыдущий период той же длины, вплотную перед текущим."""
    length = end - start + timedelta(days=1)
    return start - length, start - timedelta(days=1)


def problems(current, previous):
    """Рейтинг причин (Д7): место, изменение места, прирост, доля нерешённых, медиана времени решения."""
    total = len(current)

    def counts(df):
        return df.dropna(subset=["reason_id"]).groupby("reason_id").size()

    now, before = counts(current), counts(previous)
    if now.empty:
        return []
    rank_now = now.rank(method="min", ascending=False).astype(int)
    rank_before = before.rank(method="min", ascending=False).astype(int)
    known = current.dropna(subset=["reason_id"])
    names = known.drop_duplicates("reason_id").set_index("reason_id")[["reason", "category", "category_slug"]]
    open_share = known.groupby("reason_id")["is_open"].mean()
    resolution = known.groupby("reason_id")["hours_to_resolve"].median()

    rows = []
    for rid, count in now.items():
        prev = int(before.get(rid, 0))
        prev_rank = int(rank_before[rid]) if rid in rank_before else None
        rows.append(
            {
                "reason_id": int(rid),
                "rank": int(rank_now[rid]),
                "prev_rank": prev_rank,
                # Положительное значение: причина поднялась в рейтинге.
                "rank_change": prev_rank - int(rank_now[rid]) if prev_rank else None,
                "name": names.loc[rid, "reason"],
                "category": names.loc[rid, "category"],
                "category_slug": names.loc[rid, "category_slug"],
                "count": int(count),
                "share": count / total,
                "prev_count": prev,
                "growth": (count - prev) / prev if prev else None,
                "open_share": float(open_share[rid]),
                "median_resolution_hours": None if pd.isna(resolution[rid]) else round(float(resolution[rid]), 1),
            }
        )
    return sorted(rows, key=lambda r: (r["rank"], r["name"]))


# Изменение считается заметным, если доля изменилась не меньше чем на 20%
# и разница с ожидаемым числом не меньше 10 обращений: на малых числах 1 и 2 это ещё не рост вдвое.
NOTABLE_SHARE = 0.2
NOTABLE_COUNT = 10


def compare(base, current, base_days, current_days, by="category"):
    """Сравнение двух периодов (Д6) по категориям или причинам.

    Периоды могут быть разной длины, поэтому изменение считается по числу обращений в день.
    expected: сколько обращений было бы в текущем периоде при дневном уровне базового.
    """

    def counts(df):
        if by == "category":
            return df["category"].fillna(NO_CATEGORY).value_counts()
        known = df.dropna(subset=["reason_id"])
        return known.groupby("reason").size()

    before, now = counts(base), counts(current)
    categories = {}
    if by == "reason":
        for df in (base, current):
            categories.update(df.dropna(subset=["reason_id"]).drop_duplicates("reason").set_index("reason")["category"])

    rows = []
    for name in before.index.union(now.index):
        base_count, current_count = int(before.get(name, 0)), int(now.get(name, 0))
        base_rate, current_rate = base_count / base_days, current_count / current_days
        expected = base_rate * current_days
        change = current_rate / base_rate - 1 if base_rate else None
        if change is None:
            notable = current_count >= NOTABLE_COUNT
        else:
            notable = abs(change) >= NOTABLE_SHARE and abs(current_count - expected) >= NOTABLE_COUNT
        rows.append(
            {
                "name": name,
                "category": categories.get(name, ""),
                "base_count": base_count,
                "current_count": current_count,
                "base_per_day": round(base_rate, 2),
                "current_per_day": round(current_rate, 2),
                "expected": round(expected, 1),
                "change": change,
                "notable": notable,
            }
        )
    rows.sort(key=lambda r: (-r["current_count"], -r["base_count"], r["name"]))
    total_base, total_current = len(base), len(current)
    base_rate, current_rate = total_base / base_days, total_current / current_days
    totals = {
        "base_count": total_base,
        "current_count": total_current,
        "base_per_day": round(base_rate, 2),
        "current_per_day": round(current_rate, 2),
        "change": current_rate / base_rate - 1 if base_rate else None,
    }
    return rows, totals
