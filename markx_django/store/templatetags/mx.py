from django import template
from django.conf import settings

register = template.Library()

COLOR_HEX = {"Black": "#1b1b1d", "White": "#ecebe6", "Grey": "#808183", "Navy": "#1c2844", "Red": "#a6281c",
             "Charcoal": "#3a3b3e", "Sand": "#c4b694", "Cream": "#e8dec8", "Olive": "#4e5434"}


@register.filter
def money(v):
    try:
        return f"{settings.MARKX['CURRENCY']}{int(v):,}"
    except (TypeError, ValueError):
        return v


@register.filter
def hexcolor(name):
    return COLOR_HEX.get(name, "#999")


@register.filter
def times(n):
    return range(int(n))


@register.filter
def rest(n):
    return range(5 - int(n))


@register.simple_tag(takes_context=True)
def is_active(context, *names):
    return "active" if context.get("nav_active") in names else ""
