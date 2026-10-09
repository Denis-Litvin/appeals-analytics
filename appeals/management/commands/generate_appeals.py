"""Генератор демо-обращений из банка формулировок appeals/demo_phrases.py."""

import random
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from appeals import demo_phrases as dp
from appeals.classify import Classifier
from appeals.models import Appeal, Category, Reason, Tag
from appeals.roles import OPERATOR
from appeals.text import normalize

MSK = ZoneInfo("Europe/Moscow")

# Заложенные всплески: (сколько дней назад начался, сколько дней длился, причина, лишних обращений в день).
# Даты считаются от дня запуска, поэтому всплески всегда попадают в историю.
SPIKES = [
    (112, 1, "Пункт выдачи и постамат", 30),
    (75, 2, "Двойное списание", 26),
    (41, 3, "Приложение вылетает", 20),
    (12, 2, "Не приходит код подтверждения", 24),
]

# Относительная частота причин. Вторая цифра: во сколько раз частота меняется к концу периода.
REASON_WEIGHTS = {
    "Задержка доставки": (10, 1.4),
    "Курьер не приехал или опоздал": (7, 1.0),
    "Не проходит оплата": (7, 1.0),
    "Не приходит код подтверждения": (6, 1.0),
    "Не вернули деньги": (6, 1.1),
    "Статус заказа не обновляется": (5, 1.0),
    "Промокод не применяется": (5, 0.6),
    "Приложение вылетает": (4, 1.2),
    "Тормозит или не загружается": (4, 1.8),
    "Пункт выдачи и постамат": (4, 1.0),
    "Брак или повреждение": (4, 1.0),
    "Не могу войти в аккаунт": (4, 1.0),
    "Оформление возврата товара": (4, 1.0),
    "Прислали не тот товар": (3, 1.0),
    "Двойное списание": (3, 0.8),
    "Деньги списаны, заказ не оформлен": (3, 1.0),
    "Отмена заказа": (3, 1.0),
    "Не начислились бонусы": (3, 1.3),
    "Ошибка при оформлении заказа": (3, 1.0),
    "Долгий ответ поддержки": (3, 1.5),
    "Скидка не сработала": (2, 1.0),
    "Обмен товара": (2, 1.0),
    "Неполная комплектация": (2, 1.0),
    "Доставили не по адресу": (2, 1.0),
    "Привязка банковской карты": (2, 1.0),
    "Уведомления и рассылки": (2, 1.0),
    "Аккаунт заблокирован": (1.5, 1.0),
    "Смена телефона или почты": (1.5, 1.0),
    "Грубость сотрудника": (1.5, 1.0),
    "Удаление аккаунта": (1, 1.0),
}
UNCLEAR_SHARE = 0.09

# Будни нагружены сильнее выходных, в течение суток два пика: в обед и вечером.
WEEKDAY_FACTOR = [1.15, 1.1, 1.05, 1.0, 0.95, 0.7, 0.62]
HOUR_WEIGHTS = [
    0.8, 0.5, 0.3, 0.2, 0.2, 0.3, 0.7, 1.5, 3.0, 4.5, 5.5, 6.0,
    6.2, 6.0, 5.6, 5.3, 5.2, 5.4, 5.8, 6.3, 6.4, 5.5, 3.8, 2.0,
]
GROWTH = (0.75, 1.3)  # общий объём к концу периода растёт

CHANNELS = [("app", 0.38), ("web", 0.22), ("chat", 0.2), ("email", 0.12), ("phone", 0.08)]

# Медиана времени решения в часах по категориям, разброс логнормальный.
RESOLUTION_HOURS = {
    "payment": 20, "delivery": 30, "returns": 72, "account": 6, "app": 24,
    "promo": 12, "quality": 48, "service": 10, None: 4,
}

MANUAL_FIX_SHARE = 0.35  # доля ошибок автоопределения, которые оператор исправил вручную
MANUAL_CONFIRM_SHARE = 0.01  # оператор пересохранил верную категорию вручную

KEYBOARD_ROWS = ["йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю"]
NEIGHBOURS = {
    ch: row[max(i - 1, 0) : i] + row[i + 1 : i + 2] for row in KEYBOARD_ROWS for i, ch in enumerate(row)
}
TRANSLIT = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh sch _ y _ e yu ya".split(),
    )
)
CYR_WORD = re.compile(r"[а-яё]{4,}")


def typo(word, rnd):
    """Одна опечатка в слове. Первую букву не трогаем: её люди замечают и исправляют."""
    i = rnd.randint(1, len(word) - 1)
    kind = rnd.choice(["drop", "swap", "neighbour", "double"])
    if kind == "swap" and i < len(word) - 1:
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    if kind == "neighbour" and NEIGHBOURS.get(word[i]):
        return word[:i] + rnd.choice(NEIGHBOURS[word[i]]) + word[i + 1 :]
    if kind == "double":
        return word[: i + 1] + word[i] + word[i + 1 :]
    return word[:i] + word[i + 1 :]


def add_typos(text, rnd, count):
    for _ in range(count):
        words = list(CYR_WORD.finditer(text))
        if not words:
            break
        m = rnd.choice(words)
        text = text[: m.start()] + typo(m.group(), rnd) + text[m.end() :]
    return text


def roughen(text, rnd):
    """Как пишут на самом деле: строчными, без знаков, с опечатками, «не» слитно."""
    if rnd.random() < 0.35:
        text = text.lower()
    if rnd.random() < 0.15:
        text = re.sub(r"[.,!]", "", text)
    if rnd.random() < 0.03:
        text = re.sub(r"\b([Нн]е) (\w)", r"\1\2", text, count=1)
    roll = rnd.random()
    if roll < 0.08:
        text = add_typos(text, rnd, 2)
    elif roll < 0.33:
        text = add_typos(text, rnd, 1)
    return text


def translit(word):
    return "".join(TRANSLIT.get(ch, ch) for ch in word.lower()).replace("_", "")


@dataclass
class Draft:
    created_at: datetime
    reason: str | None
    spike: bool = False
    appeal: Appeal | None = None
    tags: list = field(default_factory=list)


@dataclass
class Stats:
    total: int = 0
    start: date | None = None
    end: date | None = None
    by_weekday: dict = field(default_factory=dict)
    by_hour: dict = field(default_factory=dict)
    by_category: Counter = field(default_factory=Counter)
    without_category: int = 0
    manual: int = 0
    intended: int = 0
    auto_correct: int = 0
    spikes: list = field(default_factory=list)
    words: list = field(default_factory=list)
    seconds: float = 0


class Generator:
    def __init__(self, seed, end):
        self.rnd = random.Random(seed)
        self.np = np.random.default_rng(seed)
        self.end = end.astimezone(MSK)
        self.reasons = {r.name: r for r in Reason.objects.select_related("category")}
        missing = set(dp.REASON_TEXTS) - set(self.reasons)
        if missing:
            raise CommandError(f"Нет причин в справочнике, сначала load_dictionary: {', '.join(sorted(missing))}")
        self.tags = {t.name: t for t in Tag.objects.all()}
        self.slugs = dict(Category.objects.values_list("id", "slug"))
        # Обращения разбирают операторы, нагрузка у них разная.
        self.assignees = list(User.objects.filter(groups__name=OPERATOR).order_by("id"))
        self.assignee_weights = [1 / (i + 1.5) for i in range(len(self.assignees))]

    def plan(self, count, months):
        """Даты и причины всех обращений, без текстов."""
        last_day = self.end.date()
        n_days = round(months * 30.44)
        days = [last_day - timedelta(days=n_days - 1 - i) for i in range(n_days)]
        spike_days = {}
        for days_ago, length, reason, extra in SPIKES:
            for k in range(length):
                d = last_day - timedelta(days=days_ago - k)
                if days[0] <= d <= last_day:
                    spike_days[(d, reason)] = extra
        base_total = count - sum(spike_days.values())
        if base_total <= 0:
            raise CommandError("Слишком маленький --count для заложенных всплесков")

        hours = np.array(HOUR_WEIGHTS) / sum(HOUR_WEIGHTS)
        weights = []
        for i, d in enumerate(days):
            t = i / max(n_days - 1, 1)
            w = (GROWTH[0] + (GROWTH[1] - GROWTH[0]) * t) * WEEKDAY_FACTOR[d.weekday()]
            weights.append(w * self.np.lognormal(0, 0.12))
        # Сегодняшний день ещё не закончился: в нём только уже прошедшие часы.
        weights[-1] *= hours[: self.end.hour + 1].sum()
        per_day = self.np.multinomial(base_total, np.array(weights) / sum(weights))

        names = list(REASON_WEIGHTS)
        drafts = []
        for i, (d, n) in enumerate(zip(days, per_day)):
            t = i / max(n_days - 1, 1)
            reason_w = [w * (1 + (trend - 1) * t) for w, trend in REASON_WEIGHTS.values()]
            for _ in range(n):
                reason = None if self.rnd.random() < UNCLEAR_SHARE else self.rnd.choices(names, reason_w)[0]
                drafts.append(Draft(self.moment(d, hours), reason))
        for (d, reason), extra in spike_days.items():
            drafts += [Draft(self.moment(d, hours), reason, spike=True) for _ in range(extra)]
        drafts.sort(key=lambda x: x.created_at)
        return drafts, days, spike_days

    def moment(self, d, hours):
        hour = int(self.np.choice(24, p=hours))
        moment = datetime(d.year, d.month, d.day, hour, self.rnd.randint(0, 59), self.rnd.randint(0, 59), tzinfo=MSK)
        if moment > self.end:
            moment = self.end - timedelta(seconds=self.rnd.randint(60, 3 * 3600))
        return moment

    def intro(self, hour):
        intro = self.rnd.choice(dp.INTROS)
        if ("утро" in intro and not 5 <= hour < 12) or ("вечер" in intro and not 17 <= hour <= 23):
            return ""
        return intro

    def text(self, reason, channel, hour):
        rnd = self.rnd
        core = dp.fill(rnd.choice(dp.REASON_TEXTS[reason] if reason else dp.UNCLEAR_TEXTS), rnd)
        if channel == "phone":
            # Звонок записывает оператор, без приветствий и подписи клиента.
            return roughen("Звонок на горячую линию. Клиент сообщает: " + core, rnd)
        if reason and rnd.random() < 0.12:
            body = dp.fill(rnd.choice(dp.LONG_FRAMES), rnd, core=core)
            if rnd.random() < 0.3:
                body += "\n\n" + rnd.choice(dp.EMOTIONS) + " " + rnd.choice([x for x in dp.OUTROS if x])
        else:
            parts = [self.intro(hour), core]
            if rnd.random() < 0.15:
                parts.append(rnd.choice(dp.EMOTIONS))
            parts.append(rnd.choice(dp.OUTROS))
            body = " ".join(p for p in parts if p)
        return roughen(body, rnd)

    def author(self, channel):
        rnd = self.rnd
        first = rnd.choice(dp.FIRST_NAMES)
        last = rnd.choice(dp.LAST_NAMES)[1 if first in dp.FEMALE_NAMES else 0]
        if channel == "phone" and rnd.random() < 0.5:
            return f"{first} {last}", ""
        login = rnd.choice(
            [f"{translit(first)}.{translit(last)}", f"{translit(first)}{rnd.randint(70, 99)}",
             f"{translit(last)}{rnd.randint(1, 999)}"]
        )
        return f"{first} {last}", f"{login}@{rnd.choice(dp.EMAIL_DOMAINS)}"

    def pick_tags(self, draft, text, channel, category_slug):
        rnd, low, tags = self.rnd, text.lower(), set()
        if re.search(r"айфон|iphone", low):
            tags.add("iOS")
        elif re.search(r"андроид|самсунг|xiaomi|honor|pixel", low):
            tags.add("Android")
        elif channel == "app" and rnd.random() < 0.5:
            tags.add(rnd.choice(["iOS", "Android", "Android"]))
        if re.search(r"второй раз|третий раз|не первый", low) or rnd.random() < 0.06:
            tags.add("Повторное")
        if "срочно" in low or rnd.random() < 0.03:
            tags.add("Срочно")
        if draft.reason == "Грубость сотрудника" and rnd.random() < 0.8:
            tags.add("Жалоба на сотрудника")
        if "не буду" in low or rnd.random() < 0.01:
            tags.add("Угроза ухода")
        if category_slug == "app" and rnd.random() < 0.3:
            tags.add("Ошибка подтверждена")
        for name, share in (("VIP", 0.03), ("Юрлицо", 0.02), ("Новый клиент", 0.05)):
            if rnd.random() < share:
                tags.add(name)
        return [self.tags[t] for t in sorted(tags) if t in self.tags]

    def status(self, created_at, category_slug, unclear):
        rnd = self.rnd
        age_days = (self.end - created_at).total_seconds() / 86400
        if age_days < 1:
            options = [("new", 0.7), ("in_work", 0.3)]
        elif age_days < 3:
            options = [("new", 0.15), ("in_work", 0.4), ("resolved", 0.4), ("closed", 0.05)]
        elif age_days < 7:
            options = [("new", 0.05), ("in_work", 0.2), ("resolved", 0.65), ("closed", 0.1)]
        else:
            options = [("in_work", 0.03), ("resolved", 0.82), ("closed", 0.15)]
        if unclear:
            options = [(s, w * (3 if s == "closed" else 1)) for s, w in options]
        status = rnd.choices([s for s, _ in options], [w for _, w in options])[0]
        if status in ("new", "in_work"):
            return status, None
        hours = RESOLUTION_HOURS.get(category_slug, 24) * float(self.np.lognormal(0, 0.9))
        resolved_at = created_at + timedelta(hours=max(hours, 0.1))
        if resolved_at > self.end:
            return "in_work", None
        return status, resolved_at

    def build(self, drafts, classifier):
        stats = Stats()
        for draft in drafts:
            channel = self.rnd.choices([c for c, _ in CHANNELS], [w for _, w in CHANNELS])[0]
            text = self.text(draft.reason, channel, draft.created_at.hour)
            subject = ""
            if channel in ("email", "web") and self.rnd.random() < 0.6:
                subject = dp.fill(self.rnd.choice(dp.SUBJECTS), self.rnd)
            name, email = self.author(channel)
            appeal = Appeal(
                created_at=draft.created_at, channel=channel, author_name=name, author_email=email,
                subject=subject, text=text,
            )
            appeal.text_norm = normalize(appeal.full_text)
            appeal.apply_classification(classifier.classify(appeal.full_text))

            intended = self.reasons.get(draft.reason)
            if intended:
                stats.intended += 1
                correct = appeal.category_id == intended.category_id
                stats.auto_correct += correct
                manual_share = MANUAL_CONFIRM_SHARE if correct else MANUAL_FIX_SHARE
                if self.rnd.random() < manual_share:
                    appeal.category_id, appeal.reason_id = intended.category_id, intended.id
                    appeal.category_source = Appeal.Source.MANUAL

            slug = self.slugs.get(appeal.category_id)
            appeal.status, appeal.resolved_at = self.status(draft.created_at, slug, draft.reason is None)
            if appeal.status != "new" and self.assignees:
                appeal.assignee = self.rnd.choices(self.assignees, self.assignee_weights)[0]
            draft.appeal = appeal
            draft.tags = self.pick_tags(draft, text, channel, slug)
        return stats


@transaction.atomic
def generate(count=6000, months=6, seed=42, end=None, clear=False):
    """Создаёт обращения и возвращает Stats. end по умолчанию текущий момент."""
    started = time.perf_counter()
    if clear:
        Appeal.objects.all().delete()
    gen = Generator(seed, end or timezone.now())
    drafts, days, spike_days = gen.plan(count, months)
    stats = gen.build(drafts, Classifier.from_db())

    appeals = Appeal.objects.bulk_create([d.appeal for d in drafts], batch_size=1000)
    links = [
        Appeal.tags.through(appeal_id=a.pk, tag_id=t.pk) for a, d in zip(appeals, drafts) for t in d.tags
    ]
    Appeal.tags.through.objects.bulk_create(links, batch_size=2000)

    stats.total = len(appeals)
    stats.start, stats.end = days[0], days[-1]
    weekday_days = Counter(d.weekday() for d in days[:-1])  # неполный последний день не берём
    weekday_count = Counter(d.created_at.weekday() for d in drafts if d.created_at.date() < days[-1])
    stats.by_weekday = {wd: weekday_count[wd] / weekday_days[wd] for wd in range(7) if weekday_days[wd]}
    stats.by_hour = Counter(d.created_at.hour for d in drafts)
    stats.by_category = Counter(gen.slugs.get(a.category_id) for a in appeals)
    stats.without_category = stats.by_category[None]
    stats.manual = sum(a.category_source == Appeal.Source.MANUAL for a in appeals)
    per_day_reason = Counter((d.created_at.date(), d.reason) for d in drafts)
    usual = defaultdict(list)
    for (day, reason), n in per_day_reason.items():
        usual[reason].append(n)
    for (day, reason), extra in sorted(spike_days.items()):
        stats.spikes.append((day, reason, per_day_reason[(day, reason)], statistics.median(usual[reason])))
    stats.words = [len(a.full_text.split()) for a in appeals]
    stats.seconds = time.perf_counter() - started
    return stats


WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def summary(stats):
    """Сводка по сгенерированным данным в виде строк для вывода в консоль."""
    lines = [
        f"Создано обращений: {stats.total} за {stats.start:%d.%m.%Y} - {stats.end:%d.%m.%Y}, "
        f"{stats.seconds:.1f} с",
        "В среднем за день по дням недели: "
        + ", ".join(f"{WEEKDAYS[wd]} {v:.0f}" for wd, v in sorted(stats.by_weekday.items())),
    ]
    night = sum(stats.by_hour[h] for h in range(0, 7))
    day = sum(stats.by_hour[h] for h in range(10, 17))
    evening = sum(stats.by_hour[h] for h in range(18, 22))
    lines.append(
        f"По времени суток: ночь 00-06 {night / stats.total:.0%}, день 10-16 {day / stats.total:.0%}, "
        f"вечер 18-21 {evening / stats.total:.0%}"
    )
    names = dict(Category.objects.values_list("slug", "name"))
    lines.append(
        "По категориям: "
        + ", ".join(
            f"{names.get(slug, 'без категории')} {n / stats.total:.0%}" for slug, n in stats.by_category.most_common()
        )
    )
    lines.append(
        f"Без категории: {stats.without_category / stats.total:.1%}, ручная категория: {stats.manual / stats.total:.1%}"
    )
    if stats.intended:
        lines.append(
            f"Автокатегория совпала с заложенной: {stats.auto_correct} из {stats.intended} "
            f"({stats.auto_correct / stats.intended:.1%})"
        )
    words = sorted(stats.words)
    lines.append(f"Длина текста в словах: от {words[0]} до {words[-1]}, медиана {statistics.median(words):.0f}")
    for day, reason, n, median in stats.spikes:
        lines.append(f"Всплеск {day:%d.%m.%Y}: {reason}, {n} обращений при обычных {median:.0f}")
    return lines


class Command(BaseCommand):
    help = "Генерирует демо-обращения. Даты отсчитываются от текущего момента."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=6000)
        parser.add_argument("--months", type=float, default=6)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--clear", action="store_true", help="удалить все обращения перед генерацией")

    def handle(self, *args, **options):
        stats = generate(options["count"], options["months"], options["seed"], clear=options["clear"])
        for line in summary(stats):
            self.stdout.write(line)
