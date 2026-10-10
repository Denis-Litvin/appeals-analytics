from django import forms
from django.contrib.auth.models import User

from .models import Appeal, Category, Reason, Tag
from .roles import OPERATOR


class ReasonSelect(forms.Select):
    """Список причин, у каждого варианта своя категория: скрипт формы прячет причины чужих категорий.
    category_field: чем категория обозначена в соседнем списке, id в форме правки, slug в фильтре."""

    def __init__(self, *args, category_field="category_id", **kwargs):
        super().__init__(*args, **kwargs)
        self.categories = dict(Reason.objects.values_list("id", category_field))

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            option["attrs"]["data-category"] = self.categories.get(int(str(value)), "")
        return option


class AssigneeField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return user.get_full_name() or user.username


class AppealCreateForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        Tag.objects.all(), required=False, widget=forms.CheckboxSelectMultiple, label="Теги"
    )

    class Meta:
        model = Appeal
        fields = ["channel", "author_name", "author_email", "subject", "text", "tags"]
        widgets = {"text": forms.Textarea(attrs={"rows": 8})}


class AppealEditForm(forms.ModelForm):
    category = forms.ModelChoiceField(Category.objects.filter(is_active=True), required=False, label="Категория")
    reason = forms.ModelChoiceField(
        Reason.objects.filter(is_active=True).select_related("category"), required=False, label="Причина"
    )
    assignee = AssigneeField(User.objects.none(), required=False, label="Исполнитель")
    tags = forms.ModelMultipleChoiceField(
        Tag.objects.all(), required=False, widget=forms.CheckboxSelectMultiple, label="Теги"
    )

    class Meta:
        model = Appeal
        fields = ["status", "assignee", "category", "reason", "tags"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].widget = ReasonSelect(choices=self.fields["reason"].choices)
        # Исполнитель выбирается из операторов. Текущий остаётся в списке, даже если уже не оператор.
        assignees = User.objects.filter(groups__name=OPERATOR)
        if self.instance.assignee_id:
            assignees = assignees | User.objects.filter(pk=self.instance.assignee_id)
        self.fields["assignee"].queryset = assignees.distinct().order_by("last_name", "first_name")

    def clean(self):
        data = super().clean()
        category, reason = data.get("category"), data.get("reason")
        if reason and not category:
            data["category"] = reason.category
        elif reason and reason.category_id != category.id:
            self.add_error("reason", f"Причина «{reason}» относится к категории «{reason.category}».")
        return data

    @property
    def category_changed(self):
        return bool({"category", "reason"} & set(self.changed_data))


class AppealFilterForm(forms.Form):
    """Фильтры списка обращений. Все поля необязательные, пустое поле не ограничивает выборку."""

    NONE = "none"
    OPEN = "open"

    q = forms.CharField(
        required=False,
        label="Поиск",
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "слова, \"фраза\", #номер или email"}),
    )
    date_from = forms.DateField(required=False, label="С", widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, label="По", widget=forms.DateInput(attrs={"type": "date"}))
    category = forms.ChoiceField(required=False, label="Категория")
    reason = forms.ModelChoiceField(
        Reason.objects.select_related("category"), required=False, label="Причина", empty_label="все"
    )
    tags = forms.ModelMultipleChoiceField(
        Tag.objects.all(), required=False, label="Теги", widget=forms.SelectMultiple(attrs={"size": 4})
    )
    channel = forms.ChoiceField(required=False, label="Канал", choices=[("", "все")] + Appeal.Channel.choices)
    status = forms.ChoiceField(
        required=False,
        label="Статус",
        choices=[("", "все"), (OPEN, "Открытые: новые и в работе")] + Appeal.Status.choices,
    )
    source = forms.ChoiceField(
        required=False, label="Источник категории", choices=[("", "все")] + Appeal.Source.choices
    )
    assignee = forms.ChoiceField(required=False, label="Исполнитель")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = (
            [("", "все"), (self.NONE, "Без категории")] + list(Category.objects.values_list("slug", "name"))
        )
        self.fields["reason"].widget = ReasonSelect(
            choices=self.fields["reason"].choices, category_field="category__slug"
        )
        operators = User.objects.filter(groups__name=OPERATOR).order_by("last_name", "first_name")
        self.fields["assignee"].choices = [("", "все"), (self.NONE, "Не назначен")] + [
            (str(u.pk), u.get_full_name() or u.username) for u in operators
        ]

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            self.add_error("date_to", "Конец периода раньше начала.")
        return data
