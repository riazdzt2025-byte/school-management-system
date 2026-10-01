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


@register.simple_tag(takes_context=True)
def retained_list_filters(context, exclude=''):
    """Keep repeated/escaped GET filters, but reset page when a filter changes.

    Names rendered by the calling filter form are excluded to avoid duplicate
    values. The normalized page size is emitted separately by the partial.
    """
    request = context.get('request')
    if request is None:
        return []
    excluded = {'page', 'print', 'per_page', *str(exclude or '').split()}
    return [
        (key, value)
        for key, values in request.GET.lists() if key not in excluded
        for value in values
    ]
