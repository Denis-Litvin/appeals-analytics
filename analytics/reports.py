"""Аналитический отчёт за период (О9).

В отчёте: сводка, категории, топ причин, динамика по дням, сравнение с предыдущим периодом той же длины,
всплески и доля обращений без категории. Выводы текстом строятся по правилам из тех же чисел, что и таблицы,
поэтому текст не может разойтись с цифрами отчёта.
"""

from . import charts, stats
from .models import SpikeAlert

TOP_REASONS = 10
SPIKES_IN_TEXT = 3
# При такой доле обращений без категории словарь стоит пополнить.
WITHOUT_CATEGORY_WARN = 0.1


def percent(value, digits=1):
    return f"{value * 100:.{digits}f}%".replace(".", ",")


def signed(value):
    """Изменение в процентах со знаком: «+125%», «-60%». Пустое значение: прошлого периода нет."""
    return "нет базы" if value is None else f"{value * 100:+.0f}%"


def number(value):
    return f"{value:g}".replace(".", ",")


def change(current, previous):
    return current / previous - 1 if previous else None


def summary_rows(now, before):
    """Сводка: показатель, текущий период, предыдущий, изменение. Значения уже в виде строк."""
    hours_now, hours_before = now.median_resolution_hours, before.median_resolution_hours
    return [
        {
            "name": "Обращений",
            "current": str(now.total),
            "previous": str(before.total),
            "change": change(now.total, before.total),
        },
        {
            "name": "В среднем в день",
            "current": number(now.per_day),
            "previous": number(before.per_day),
            "change": change(now.per_day, before.per_day),
        },
        {
            "name": "Открытые: новые и в работе",
            "current": str(now.open_count),
            "previous": str(before.open_count),
            "change": change(now.open_count, before.open_count),
        },
        {
            "name": "Без категории",
            "current": f"{now.without_category} ({percent(now.without_category_share)})",
            "previous": f"{before.without_category} ({percent(before.without_category_share)})",
            "change": change(now.without_category, before.without_category),
        },
        {
            "name": "Медиана времени решения",
            "current": f"{number(hours_now)} ч" if hours_now is not None else "нет данных",
            "previous": f"{number(hours_before)} ч" if hours_before is not None else "нет данных",
            "change": change(hours_now, hours_before) if hours_now is not None and hours_before else None,
        },
    ]


def period_alerts(form, start, end):
    """Уведомления о росте за период. При фильтре по категории только её уведомления."""
    alerts = SpikeAlert.objects.filter(day__range=(start, end)).select_related("category", "reason")
    category = form.cleaned_data.get("category")
    if category == "none":
        return []
    if category:
        alerts = alerts.filter(category__slug=category)
    return list(alerts.order_by("day", "-ratio"))


def build(form):
    """Все данные отчёта. Если за период нет обращений, остаётся только сводка."""
    start, end = form.period
    prev_start, prev_end = stats.previous_period(start, end)
    current = stats.load_frame(form.appeals())
    previous = stats.load_frame(form.appeals(prev_start, prev_end))
    now, before = stats.summary(current, start, end), stats.summary(previous, prev_start, prev_end)
    report = {
        "start": start,
        "end": end,
        "prev_start": prev_start,
        "prev_end": prev_end,
        "summary": now,
        "previous": before,
        "summary_rows": summary_rows(now, before),
    }
    if not len(current):
        return report

    days = now.days
    categories, totals = stats.compare(previous, current, days, days, by="category")
    for row in categories:
        row["share"] = row["current_count"] / now.total
    alerts = period_alerts(form, start, end)
    base = charts.link_base(form)
    report.update(
        categories=categories,
        totals=totals,
        reasons=stats.problems(current, previous)[:TOP_REASONS],
        alerts=alerts,
        notable_share=stats.NOTABLE_SHARE,
        notable_count=stats.NOTABLE_COUNT,
        charts={
            "daily": charts.daily(current, start, end, base, [a for a in alerts if not a.reason_id]),
            "categories": charts.categories(current, base),
            "reasons": charts.reasons(current, base, TOP_REASONS),
        },
    )
    report["conclusions"] = conclusions(report)
    return report


def conclusions(report):
    """Выводы по правилам. Каждый вывод опирается на числа из таблиц этого же отчёта."""
    now, before = report["summary"], report["previous"]
    lines = []

    text = f"Всего обращений за период: {now.total}, в среднем {number(now.per_day)} в день."
    if before.total:
        diff = change(now.total, before.total)
        if abs(diff) < 0.05:
            text += f" Это почти столько же, сколько в предыдущем периоде ({before.total})."
        else:
            more = "больше" if diff > 0 else "меньше"
            text += f" Это на {abs(diff) * 100:.0f}% {more}, чем в предыдущем периоде ({before.total})."
    else:
        text += " В предыдущем периоде обращений не было, сравнивать не с чем."
    lines.append(text)

    known = [r for r in report["categories"] if r["name"] != stats.NO_CATEGORY and r["current_count"]]
    if known:
        top = max(known, key=lambda r: r["current_count"])
        lines.append(
            f"Больше всего обращений в категории «{top['name']}»: {top['current_count']}, "
            f"{percent(top['current_count'] / now.total)} от всех."
        )

    notable = [r for r in report["categories"] if r["notable"] and r["name"] != stats.NO_CATEGORY]
    growing = [r for r in notable if r["change"] is not None and r["change"] > 0]
    falling = [r for r in notable if r["change"] is not None and r["change"] < 0]
    new = [r for r in notable if r["change"] is None]
    if growing:
        top = max(growing, key=lambda r: r["change"])
        lines.append(
            f"Сильнее всего выросла категория «{top['name']}»: было {top['base_count']}, "
            f"стало {top['current_count']}, {signed(top['change'])}."
        )
    elif not new:
        lines.append("Заметного роста по категориям нет.")
    for row in new:
        lines.append(
            f"Появилась категория «{row['name']}»: {row['current_count']} за период, раньше таких обращений не было."
        )
    if falling:
        top = min(falling, key=lambda r: r["change"])
        lines.append(
            f"Сильнее всего снизилась категория «{top['name']}»: было {top['base_count']}, "
            f"стало {top['current_count']}, {signed(top['change'])}."
        )

    reasons = report["reasons"]
    if reasons:
        top = reasons[0]
        text = f"Самая частая причина: «{top['name']}» ({top['category']}), за период {top['count']}"
        if top["prev_count"]:
            text += f", в предыдущем периоде {top['prev_count']} ({signed(top['growth'])})."
        else:
            text += ", в предыдущем периоде таких не было."
        lines.append(text)

    alerts = report["alerts"]
    if alerts:
        shown = [
            f"{a.day:%d.%m} {a.reason or a.category} ({a.count} при норме {number(round(a.baseline, 1))})"
            for a in sorted(alerts, key=lambda a: -a.ratio)[:SPIKES_IN_TEXT]
        ]
        lines.append(f"Резкий рост за период: {len(alerts)}. Самые сильные: {'; '.join(shown)}.")
    else:
        lines.append("Резкого роста обращений за период не было.")

    text = f"Обращений без категории: {now.without_category}, {percent(now.without_category_share)}."
    if now.without_category_share >= WITHOUT_CATEGORY_WARN:
        text += " Их стоит разобрать вручную и дополнить словарь ключевых фраз."
    lines.append(text)

    text = f"Открытых обращений: {now.open_count}, {percent(now.open_share)}."
    if now.median_resolution_hours is not None:
        text += f" Медиана времени решения {number(now.median_resolution_hours)} ч"
        if before.median_resolution_hours is not None:
            text += f", в предыдущем периоде {number(before.median_resolution_hours)} ч"
        text += "."
    lines.append(text)
    return lines
