"""Фильтры обращений по GET-параметрам. Один модуль для списка, выгрузки, отчёта и API."""

import re
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from .forms import AppealFilterForm
from .models import Appeal
from .text import STOP_WORDS, stem, tokens

NUMBER_RE = re.compile(r"^#\s*(\d+)$")
PHRASE_RE = re.compile(r'"([^"]+)"')
OPEN_STATUSES = (Appeal.Status.NEW, Appeal.Status.IN_WORK)


def starts_word(prefix):
    """В text_norm основы разделены пробелами: ищем слово, которое начинается с prefix."""
    return Q(text_norm__startswith=prefix) | Q(text_norm__contains=" " + prefix)


def text_query(q):
    """Условие для строки поиска.

    #1234 ищет по номеру обращения, строка с @ по email автора. Фраза в кавычках ищется как идущие подряд
    основы. Остальные слова ищутся каждое по началу основы, все вместе через И, служебные слова пропускаются.
    """
    q = q.strip()
    number = NUMBER_RE.match(q)
    if number:
        return Q(pk=int(number.group(1)))
    if "@" in q:
        return Q(author_email__icontains=q)
    condition = Q()
    for phrase in PHRASE_RE.findall(q):
        phrase_stems = [stem(w) for w in tokens(phrase)]
        if phrase_stems:
            condition &= starts_word(" ".join(phrase_stems))
    rest = PHRASE_RE.sub(" ", q)
    for word in tokens(rest):
        if word not in STOP_WORDS:
            condition &= starts_word(stem(word))
    return condition


def day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def apply_filters(queryset, data):
    """Накладывает на queryset проверенные значения формы фильтров."""
    if data.get("q"):
        queryset = queryset.filter(text_query(data["q"]))
    # Сутки считаются по Москве, сравнение по диапазону времени использует индекс created_at.
    if data.get("date_from"):
        queryset = queryset.filter(created_at__gte=day_start(data["date_from"]))
    if data.get("date_to"):
        queryset = queryset.filter(created_at__lt=day_start(data["date_to"] + timedelta(days=1)))
    category = data.get("category")
    if category == AppealFilterForm.NONE:
        queryset = queryset.filter(category__isnull=True)
    elif category:
        queryset = queryset.filter(category__slug=category)
    if data.get("reason"):
        queryset = queryset.filter(reason=data["reason"])
    if data.get("tags"):
        # Подходит обращение хотя бы с одним из выбранных тегов. Подзапрос не размножает строки.
        tagged = Appeal.tags.through.objects.filter(tag__in=data["tags"]).values("appeal_id")
        queryset = queryset.filter(pk__in=tagged)
    if data.get("channel"):
        queryset = queryset.filter(channel=data["channel"])
    status = data.get("status")
    if status == AppealFilterForm.OPEN:
        queryset = queryset.filter(status__in=OPEN_STATUSES)
    elif status:
        queryset = queryset.filter(status=status)
    if data.get("source"):
        queryset = queryset.filter(category_source=data["source"])
    assignee = data.get("assignee")
    if assignee == AppealFilterForm.NONE:
        queryset = queryset.filter(assignee__isnull=True)
    elif assignee:
        queryset = queryset.filter(assignee_id=int(assignee))
    return queryset


def filter_appeals(params, queryset=None):
    """Возвращает (отфильтрованный queryset, форма). Ошибочное поле пропускается, остальные применяются."""
    form = AppealFilterForm(params)
    form.is_valid()
    queryset = Appeal.objects.all() if queryset is None else queryset
    return apply_filters(queryset, form.cleaned_data), form

