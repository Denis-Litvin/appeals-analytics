from django import template

register = template.Library()


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


@register.filter
def heat(value, peak):
    """Насыщенность клетки тепловой карты от 0 до 1."""
    return f"{value / peak:.2f}" if peak else "0"
