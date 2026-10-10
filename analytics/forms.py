from datetime import timedelta

from django import forms
from django.utils import timezone

from appeals.filters import apply_filters
from appeals.forms import AppealFilterForm
from appeals.models import Appeal, Category

DEFAULT_DAYS = 30
MAX_DAYS = 366


class PeriodForm(forms.Form):
    """Период и основные срезы для аналитических страниц. Без дат берутся последние 30 дней."""

    date_from = forms.DateField(required=False, label="С", widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, label="По", widget=forms.DateInput(attrs={"type": "date"}))
    category = forms.ChoiceField(required=False, label="Категория")
    channel = forms.ChoiceField(required=False, label="Канал", choices=[("", "все")] + Appeal.Channel.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "все"), (AppealFilterForm.NONE, "Без категории")] + list(
            Category.objects.values_list("slug", "name")
        )

    def clean(self):
        data = super().clean()
        today = timezone.localdate()
        end = data.get("date_to") or today
        start = data.get("date_from") or end - timedelta(days=DEFAULT_DAYS - 1)
        if start > end:
            self.add_error("date_to", "Конец периода раньше начала.")
            start, end = end - timedelta(days=DEFAULT_DAYS - 1), end
        if (end - start).days >= MAX_DAYS:
            self.add_error("date_from", f"Период не длиннее {MAX_DAYS} дней.")
            start = end - timedelta(days=MAX_DAYS - 1)
        data["date_from"], data["date_to"] = start, end
        return data

    @property
    def period(self):
        return self.cleaned_data["date_from"], self.cleaned_data["date_to"]

    def appeals(self, start=None, end=None):
        """Обращения за период формы или за другой период с теми же срезами."""
        data = dict(self.cleaned_data)
        if start:
            data["date_from"], data["date_to"] = start, end
        return apply_filters(Appeal.objects.all(), data)


def period_form(params):
    """Форма уже проверена. Неверная дата заменяется значением по умолчанию в clean()."""
    form = PeriodForm(params)
    form.is_valid()
    return form


class CompareForm(forms.Form):
    """Два периода для сравнения (Д6). Пресеты берут последние N дней и столько же дней перед ними."""

    PRESETS = {"week": 7, "month": 30}

    preset = forms.ChoiceField(
        required=False,
        label="Что сравнить",
        choices=[("week", "Неделя к неделе"), ("month", "Месяц к месяцу"), ("custom", "Произвольные периоды")],
    )
    base_from = forms.DateField(required=False, label="Базовый период с")
    base_to = forms.DateField(required=False, label="по")
    current_from = forms.DateField(required=False, label="Текущий период с")
    current_to = forms.DateField(required=False, label="по")
    category = forms.ChoiceField(required=False, label="Категория")
    channel = forms.ChoiceField(required=False, label="Канал", choices=[("", "все")] + Appeal.Channel.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "все"), (AppealFilterForm.NONE, "Без категории")] + list(
            Category.objects.values_list("slug", "name")
        )

    def clean(self):
        data = super().clean()
        preset = data.get("preset") or "week"
        dates = [data.get(name) for name in ("base_from", "base_to", "current_from", "current_to")]
        if preset == "custom" and not all(dates):
            self.add_error("preset", "Для произвольного сравнения нужны все четыре даты.")
            preset = "week"
        if preset == "custom":
            base_from, base_to, current_from, current_to = dates
            if base_from > base_to or current_from > current_to:
                self.add_error("preset", "В одном из периодов конец раньше начала.")
                preset = "week"
        if preset != "custom":
            current_to = timezone.localdate()
            current_from = current_to - timedelta(days=self.PRESETS[preset] - 1)
            base_to = current_from - timedelta(days=1)
            base_from = base_to - timedelta(days=self.PRESETS[preset] - 1)
        data.update(
            preset=preset, base_from=base_from, base_to=base_to, current_from=current_from, current_to=current_to
        )
        return data

    @property
    def base(self):
        return self.cleaned_data["base_from"], self.cleaned_data["base_to"]

    @property
    def current(self):
        return self.cleaned_data["current_from"], self.cleaned_data["current_to"]

    def appeals(self, start, end):
        data = {"category": self.cleaned_data.get("category"), "channel": self.cleaned_data.get("channel")}
        return apply_filters(Appeal.objects.all(), {**data, "date_from": start, "date_to": end})


def compare_form(params):
    form = CompareForm(params)
    form.is_valid()
    return form
