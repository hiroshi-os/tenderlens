from django import template

register = template.Library()


@register.filter
def inr(value):
    if value is None or value == "":
        return "—"
    quantized = f"{value:,.0f}"
    return f"₹{quantized}"
