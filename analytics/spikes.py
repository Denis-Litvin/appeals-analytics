"""Поиск резкого роста обращений (Д8).

Для каждой категории и причины считается число обращений по дням (сутки московские). Обычный уровень дня:
медиана за 28 предыдущих дней с поправкой на день недели. Разброс: MAD × 1,4826. День считается всплеском,
если выполнены три условия сразу:
- обращений не меньше чем вдвое больше обычного;
- превышение не меньше MIN_EXCESS (8 для категории, 5 для причины), чтобы рост с 1 до 3 не считался всплеском;
- (число - обычный уровень) / (разброс + 1) >= 3, то есть рост выходит за обычные колебания.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pandas as pd
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Min, Q
from django.utils import timezone

from appeals.models import Appeal, Reason

from .models import SpikeAlert

TZ = "Europe/Moscow"
WINDOW = 28
MIN_HISTORY = 14  # без двух недель истории обычный уровень не считаем
MIN_RATIO = 2.0
MIN_EXCESS = {"category": 8, "reason": 5}
MIN_SCORE = 3.0
MAD_SCALE = 1.4826


@dataclass
class Spike:
    day: date
    category_id: int
    reason_id: int | None
    count: int
    baseline: float

    @property
    def ratio(self):
        # При нулевом обычном уровне рост считаем от одного обращения в день.
        return round(self.count / max(self.baseline, 1.0), 2)


def load(start, end, category_ids=None, reason_ids=None):
    """Обращения с категорией за период истории и проверки."""
    since = timezone.make_aware(datetime.combine(start - timedelta(days=WINDOW), time.min))
    until = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
    qs = Appeal.objects.filter(created_at__gte=since, created_at__lt=until, category__isnull=False)
    if category_ids or reason_ids:
        qs = qs.filter(Q(category_id__in=category_ids or []) | Q(reason_id__in=reason_ids or []))
    df = pd.DataFrame(list(qs.values_list("created_at", "category_id", "reason_id")),
                      columns=["created_at", "category_id", "reason_id"])
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert(TZ)
    df["day"] = pd.to_datetime(df["created_at"].dt.date)
    return df


def daily(df, key, start, end):
    """Таблица день × значение ключа с нулями в пустых днях."""
    days = pd.date_range(start - timedelta(days=WINDOW), end, freq="D")
    known = df.dropna(subset=[key])
    if known.empty:
        return pd.DataFrame(index=days)
    table = known.groupby(["day", key]).size().unstack(fill_value=0)
    table.columns = table.columns.astype(int)
    return table.reindex(days, fill_value=0)


def weekday_factors(totals):
    """Во сколько раз день недели загружен сильнее среднего по окну. Без поправки понедельники давали ложные всплески."""
    mean = totals.mean()
    if not mean:
        return {wd: 1.0 for wd in range(7)}
    by_weekday = totals.groupby(totals.index.weekday).mean()
    return {wd: float(by_weekday.get(wd, mean) / mean) for wd in range(7)}


def elapsed_share(df, now):
    """Какая доля суточного потока обычно приходит до текущего момента. Нужна для неполного сегодняшнего дня."""
    if df.empty:
        return 1.0
    hours = df["created_at"].dt.hour
    share = (hours < now.hour).mean() + (hours == now.hour).mean() * (now.minute / 60)
    return max(float(share), 1 / 48)


def find(table, start, end, level, totals=None, today=None, today_share=1.0, first_day=None):
    """Всплески в таблице день × ключ за дни start..end.

    totals: все обращения по дням для поправки на день недели. first_day: день первого обращения в базе,
    пустые дни до него в историю не входят, иначе первые недели данных выглядят ростом с нуля.
    """
    found = []
    min_excess = MIN_EXCESS[level]
    for day in pd.date_range(start, end, freq="D"):
        since = day - timedelta(days=WINDOW)
        if first_day is not None:
            since = max(since, pd.Timestamp(first_day))
        window = slice(since, day - timedelta(days=1))
        history = table.loc[window]
        if len(history) < MIN_HISTORY or table.empty:
            continue
        median = history.median()
        spread = (history - median).abs().median() * MAD_SCALE
        factor = weekday_factors(totals.loc[window])[day.weekday()] if totals is not None else 1.0
        expected = median * factor
        if today and day.date() == today:
            expected, spread = expected * today_share, spread * today_share
        counts = table.loc[day]
        hit = (
            (counts >= MIN_RATIO * expected)
            & (counts - expected >= min_excess)
            & ((counts - expected) / (spread + 1) >= MIN_SCORE)
        )
        for key in counts[hit].index:
            found.append((day.date(), int(key), int(counts[key]), round(float(expected[key]), 2)))
    return found


def detect(start, end, category_ids=None, reason_ids=None, now=None):
    """Всплески за дни start..end по категориям и причинам."""
    now = (now or timezone.now()).astimezone(timezone.get_current_timezone())
    df = load(start, end, category_ids, reason_ids)
    if df.empty:
        return []
    days = pd.date_range(start - timedelta(days=WINDOW), end, freq="D")
    total = df.groupby("day").size().reindex(days, fill_value=0)
    today = now.date()
    history = df[df["day"] < pd.Timestamp(today)]
    share = elapsed_share(history[history["day"] >= pd.Timestamp(today - timedelta(days=WINDOW))], now)
    reason_category = dict(Reason.objects.values_list("id", "category_id"))
    first = Appeal.objects.aggregate(first=Min("created_at"))["first"]
    first_day = timezone.localtime(first).date()
    spikes = []
    for level, key in (("category", "category_id"), ("reason", "reason_id")):
        table = daily(df, key, start, end)
        if category_ids or reason_ids:
            wanted = set(category_ids or []) if level == "category" else set(reason_ids or [])
            table = table[[c for c in table.columns if c in wanted]]
        for day, key_id, count, expected in find(table, start, end, level, total, today, share, first_day):
            if level == "category":
                spikes.append(Spike(day, key_id, None, count, expected))
            else:
                spikes.append(Spike(day, reason_category[key_id], key_id, count, expected))
    return spikes


def save(spikes):
    """Записывает всплески. На день и цель одно уведомление: повторная проверка обновляет число. Возвращает новые."""
    created = []
    for spike in spikes:
        alert, is_new = SpikeAlert.objects.update_or_create(
            category_id=spike.category_id,
            reason_id=spike.reason_id,
            day=spike.day,
            defaults={"count": spike.count, "baseline": spike.baseline, "ratio": spike.ratio},
        )
        if is_new:
            created.append(alert)
    return created


def analysts_emails():
    users = User.objects.filter(is_active=True).exclude(email="")
    return sorted(u.email for u in users if u.has_perm("appeals.view_analytics"))


def notify(alerts):
    """Письмо аналитикам о новых уведомлениях. В демо почта пишется в консоль."""
    recipients = analysts_emails()
    if not alerts or not recipients:
        return 0
    lines = []
    for alert in alerts:
        target = f"{alert.category}: {alert.reason}" if alert.reason_id else f"категория {alert.category}"
        lines.append(f"{alert.day:%d.%m.%Y}, {target}: {alert.count} обращений при обычных {alert.baseline:g}")
    send_mail(
        subject=f"Резкий рост обращений: {len(alerts)}",
        message="Найден резкий рост обращений.\n\n" + "\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
    )
    return len(recipients)


def check(start, end, notify_new=False, **kwargs):
    alerts = save(detect(start, end, **kwargs))
    if notify_new:
        notify(alerts)
    return alerts


def check_appeal(appeal):
    """Проверка после нового обращения: только его категория и причина за сегодня."""
    if not appeal.category_id:
        return []
    today = timezone.localdate()
    return check(
        today, today, notify_new=True,
        category_ids=[appeal.category_id], reason_ids=[appeal.reason_id] if appeal.reason_id else [],
    )
