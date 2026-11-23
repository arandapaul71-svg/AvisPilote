from django import template

register = template.Library()


@register.filter
def duree(delta):
    """timedelta → « 3 h », « 2 j 4 h », « 25 min »."""
    if delta is None:
        return "–"
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    heures = minutes // 60
    if heures < 24:
        return f"{heures} h"
    jours, reste = divmod(heures, 24)
    return f"{jours} j {reste} h" if reste else f"{jours} j"
