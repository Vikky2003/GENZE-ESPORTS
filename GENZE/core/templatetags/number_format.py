# core/templatetags/number_format.py
from django import template

register = template.Library()

@register.filter
def k_format(value):
    """
    Formats numbers into 'K' notation for thousands.
    Example: 1500 -> '1.5K', 2000 -> '2K'
    """
    try:
        value = int(value)
    except (ValueError, TypeError):
        return value

    if value >= 1000:
        if value % 1000 == 0:
            return f"{value // 1000}K"
        else:
            return f"{value / 1000:.1f}K"
    return str(value)

@register.filter
def mul(value, arg):
    """
    Multiplies the given value by the provided argument.
    Example: {{ teams_count|mul:4 }} -> teams_count * 4
    """
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return ''