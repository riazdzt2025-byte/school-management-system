"""Bounded, user-selectable UI pagination (OF-02).

Filter/permission scoping and deterministic ordering belong to the caller.
Exports never use this helper; only explicitly printable reports may opt into
an unpaginated ``?print=1`` view after applying exactly the same scope/filters.
"""
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator


MAX_PAGE_SIZE = 100


def get_page_size(raw):
    """Default to 100; allow any integer from 1 to 100, never a larger page."""
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return MAX_PAGE_SIZE
    return min(size, MAX_PAGE_SIZE) if size > 0 else MAX_PAGE_SIZE


def paginate_list(request, rows, *, allow_full_print=False):
    paginator = Paginator(rows, get_page_size(request.GET.get('per_page')))
    is_print_view = allow_full_print and request.GET.get('print') == '1'
    page_obj = paginator.get_page(None if is_print_view else request.GET.get('page'))
    return {
        'page_rows': rows if is_print_view else page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': not is_print_view and page_obj.has_other_pages(),
        'is_print_view': is_print_view,
    }


class SafePaginator(Paginator):
    """The admin calls ``page()`` directly; give it the same safe fallback."""

    def page(self, number):
        try:
            number = self.validate_number(number)
        except PageNotAnInteger:
            number = 1
        except EmptyPage:
            number = self.num_pages
        return super().page(number)
