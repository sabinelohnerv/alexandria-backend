from django import template
from builtins import sum as builtin_sum, zip as builtin_zip

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def div(value, arg):
    """Divide value by arg"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def sum(value):
    """Sum all values in a list"""
    try:
        return builtin_sum(float(v) for v in value)
    except (ValueError, TypeError):
        return 0

@register.filter
def zip_lists(list1, list2):
    """Zip two lists together"""
    return builtin_zip(list1, list2)
