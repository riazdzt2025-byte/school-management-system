from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key."""
    if isinstance(dictionary, dict):
        return dictionary.get(str(key))
    return None

@register.filter
def get_nested(obj, attr):
    """Get a nested attribute from an object."""
    if hasattr(obj, attr):
        return getattr(obj, attr)
    if isinstance(obj, dict):
        return obj.get(attr)
    return None
