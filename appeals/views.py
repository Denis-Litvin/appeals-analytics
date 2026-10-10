import re
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from analytics.spikes import check_appeal

from .classify import Classifier
from .filters import filter_appeals
from .forms import AppealCreateForm, AppealEditForm
from .models import Appeal, Reason
from .roles import author_for
from .text import phrase_stems, stem

CLOSED_STATUSES = (Appeal.Status.RESOLVED, Appeal.Status.CLOSED)

PAGE_SIZE = 50
SIMILAR_DAYS = 7
SIMILAR_LIMIT = 5
ORDERINGS = {"new": ("-created_at", "-id"), "old": ("created_at", "id")}
WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")


@permission_required("appeals.view_appeal", raise_exception=True)
def appeal_list(request):
    order = request.GET.get("order", "new")
    if order not in ORDERINGS:
        order = "new"
    appeals, form = filter_appeals(request.GET)
    appeals = (
        appeals.select_related("category", "reason")
        .prefetch_related("tags")
        .defer("text_norm", "category_matches", "author_name", "author_email")
        .order_by(*ORDERINGS[order])
    )
    page = Paginator(appeals, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "appeals/list.html", {"page": page, "order": order, "form": form})


def highlight(text, stems):
    """Выделяет в тексте слова, основы которых входят в найденные ключевые фразы."""
    parts, last = [], 0
    for m in WORD_RE.finditer(text):
        parts.append(escape(text[last : m.start()]))
        word = m.group()
        if stem(word.lower().replace("ё", "е")) in stems:
            parts.append(f"<mark>{escape(word)}</mark>")
        else:
            parts.append(escape(word))
        last = m.end()
    parts.append(escape(text[last:]))
    return mark_safe("".join(parts))


@permission_required("appeals.view_appeal", raise_exception=True)
def appeal_detail(request, pk):
    appeal = get_object_or_404(
        Appeal.objects.select_related("category", "reason", "assignee").prefetch_related("tags"), pk=pk
    )
    author_name, author_email = author_for(request.user, appeal)

    reasons = Reason.objects.select_related("category").in_bulk({m["reason"] for m in appeal.category_matches})
    matches = [
        {**m, "reason_obj": reasons.get(m["reason"])}
        for m in sorted(appeal.category_matches, key=lambda m: -m["weight"])
    ]
    winning = [m for m in matches if m["reason_obj"] and m["reason_obj"].category_id == appeal.category_id]
    marked = {s for m in winning for s in phrase_stems(m["phrase"])} - {"не"}

    similar = []
    if appeal.reason_id:
        window = timedelta(days=SIMILAR_DAYS)
        similar = (
            Appeal.objects.filter(
                reason_id=appeal.reason_id,
                created_at__gte=appeal.created_at - window,
                created_at__lte=appeal.created_at + window,
            )
            .exclude(pk=appeal.pk)
            .only("id", "created_at", "text", "status")
            .order_by("-created_at")[:SIMILAR_LIMIT]
        )

    return render(
        request,
        "appeals/detail.html",
        {
            "appeal": appeal,
            "author_name": author_name,
            "author_email": author_email,
            "text_html": highlight(appeal.text, marked),
            "matches": matches,
            "similar": similar,
            "similar_days": SIMILAR_DAYS,
        },
    )


def category_label(appeal):
    if not appeal.category_id:
        return "без категории"
    return f"{appeal.category}, {appeal.reason}" if appeal.reason_id else str(appeal.category)


@permission_required("appeals.add_appeal", raise_exception=True)
def appeal_create(request):
    form = AppealCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        appeal = form.save()
        messages.success(request, f"Обращение № {appeal.pk} создано. Категория: {category_label(appeal)}.")
        for alert in check_appeal(appeal):
            messages.warning(request, f"Резкий рост: {alert}. Аналитикам отправлено уведомление.")
        return redirect("appeals:detail", appeal.pk)
    return render(request, "appeals/form.html", {"form": form, "title": "Новое обращение"})


@permission_required("appeals.change_appeal", raise_exception=True)
def appeal_edit(request, pk):
    appeal = get_object_or_404(Appeal, pk=pk)
    form = AppealEditForm(request.POST or None, instance=appeal)
    if request.method == "POST" and form.is_valid():
        appeal = form.save(commit=False)
        if form.category_changed:
            appeal.category_source = Appeal.Source.MANUAL
            appeal.category_score = 0
        if appeal.status in CLOSED_STATUSES and not appeal.resolved_at:
            appeal.resolved_at = timezone.now()
        elif appeal.status not in CLOSED_STATUSES:
            appeal.resolved_at = None
        if appeal.status != Appeal.Status.NEW and not appeal.assignee_id:
            appeal.assignee = request.user
        appeal.save()
        form.save_m2m()
        messages.success(request, "Изменения сохранены.")
        return redirect("appeals:detail", appeal.pk)
    return render(request, "appeals/form.html", {"form": form, "appeal": appeal, "title": f"Обращение № {appeal.pk}"})


@require_POST
@permission_required("appeals.change_appeal", raise_exception=True)
def appeal_auto_category(request, pk):
    """Снимает ручную категорию и возвращает определение по словарю."""
    appeal = get_object_or_404(Appeal, pk=pk)
    appeal.apply_classification(Classifier.from_db().classify(appeal.full_text))
    appeal.save()
    messages.success(request, f"Категория определена по словарю: {category_label(appeal)}.")
    return redirect("appeals:detail", appeal.pk)
