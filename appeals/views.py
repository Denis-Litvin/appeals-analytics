import re
from datetime import timedelta

from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .models import Appeal, Reason
from .roles import author_for
from .text import phrase_stems, stem

PAGE_SIZE = 50
SIMILAR_DAYS = 7
SIMILAR_LIMIT = 5
ORDERINGS = {"new": ("-created_at", "-id"), "old": ("created_at", "id")}
WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")


@permission_required("appeals.view_appeal", raise_exception=True)
def appeal_list(request):
    order = request.GET.get("order", "new")
    appeals = (
        Appeal.objects.select_related("category", "reason")
        .prefetch_related("tags")
        .defer("text_norm", "category_matches", "author_name", "author_email")
        .order_by(*ORDERINGS.get(order, ORDERINGS["new"]))
    )
    page = Paginator(appeals, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "appeals/list.html", {"page": page, "order": order if order in ORDERINGS else "new"})


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
