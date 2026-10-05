"""Apply the same UI cap to reference lists that live only in Django admin."""
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList

from .pagination import SafePaginator, get_page_size


class BoundedChangeList(ChangeList):
    def get_filters_params(self, params=None):
        lookup_params = super().get_filters_params(params)
        # This is a display option, never an ORM lookup/filter.
        lookup_params.pop('per_page', None)
        return lookup_params

    def get_results(self, request):
        self.list_per_page = get_page_size(request.GET.get('per_page'))
        self.show_all = False  # ?all must not bypass the owner's hard cap.
        super().get_results(request)
        self.can_show_all = False
        self.page_num = self.paginator.get_page(self.page_num).number


class BoundedModelAdmin(admin.ModelAdmin):
    change_list_template = 'admin/students/paginated_change_list.html'
    paginator = SafePaginator
    list_max_show_all = 0

    def get_changelist(self, request, **kwargs):
        return BoundedChangeList
