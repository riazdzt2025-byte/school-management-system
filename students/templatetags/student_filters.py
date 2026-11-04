import re

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


@register.filter
def ordinal(value):
    """Format a merit position for the paper register (1st, 2nd, 11th…).

    Keep the calculated position numeric in the view; this is display-only.
    Unranked students retain the register's em dash, not a made-up place.
    """
    if value is None or value == '':
        return '—'
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    if number < 1:
        return value
    suffix = 'th' if number % 100 in (11, 12, 13) else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


@register.filter
def class_label(value):
    """Spell out a numeric class on the printed heading, as on the school's sheet."""
    labels = {
        '1': 'One', '2': 'Two', '3': 'Three', '4': 'Four', '5': 'Five',
        '6': 'Six', '7': 'Seven', '8': 'Eight', '9': 'Nine', '10': 'Ten',
        '11': 'Eleven', '12': 'Twelve',
    }
    return labels.get(str(value), value)


@register.filter
def class_padded_label(value):
    """Class cell of the published-result sheet: '6' -> '06 (Six)', '10' -> '10 (Ten)'.

    The school's published-result printout writes the class zero-padded and
    spelled out in parentheses; non-numeric class values pass through unchanged.
    """
    raw = '' if value is None else str(value).strip()
    if raw.isdigit():
        return f'{int(raw):02d} ({class_label(raw)})'
    return raw


@register.filter
def school_only(value):
    """The school part of an institution name on a printed document.

    Institution rows are named for the whole organisation ("… School And
    College"), but a school paper must never print the college: the printed
    headings show "… School" alone, and the college keeps its own name where a
    college document is printed.
    """
    raw = '' if value is None else str(value).strip()
    stripped = re.sub(r'\s*(?:&|and)\s*college\s*$', '', raw, flags=re.IGNORECASE).strip()
    return stripped or raw


@register.filter
def college_only(value):
    """The college counterpart of :func:`school_only`.

    "… School And College" prints as "… College", so a college document never
    carries the school's name either — the two are always kept apart.
    """
    raw = '' if value is None else str(value).strip()
    match = re.search(r'^(?P<base>.*?)\s*(?:&|and)\s*college\s*$', raw, flags=re.IGNORECASE)
    if not match:
        return raw
    base = re.sub(r'\s+school$', '', match.group('base').strip(), flags=re.IGNORECASE).strip()
    return f'{base} College' if base else raw


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
