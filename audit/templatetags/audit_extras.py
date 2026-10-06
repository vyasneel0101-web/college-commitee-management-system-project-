from django import template

from ..models import ACTION_LABELS

register = template.Library()


@register.filter
def audit_label(action):
    """Readable name for a recorded action; unknown values print as stored."""
    return ACTION_LABELS.get(action, action)
