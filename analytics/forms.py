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
