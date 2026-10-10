from django import template
from django.urls import reverse

from analytics.charts import PLOTLY_VERSION

register = template.Library()


@register.simple_tag
def plotly_src():
    """Адрес plotly.js с версией пакета: при обновлении plotly браузер загрузит новый файл."""
    return reverse("analytics:plotly_js", args=[PLOTLY_VERSION])


@register.filter
def percent(value, digits=1):
    """Доля 0..1 в виде «12,3%»."""
    if value is None:
        return ""
    return f"{value * 100:.{digits}f}%".replace(".", ",")


@register.filter
def hours(value):
    if value is None:
        return "нет данных"
    return f"{value:.1f} ч".replace(".", ",")


@register.filter
def signed_percent(value):
    """Прирост: «+25%», «-40%». Пустое значение означает, что в прошлом периоде таких не было."""
    if value is None:
        return "новая"
    return f"{value * 100:+.0f}%"
