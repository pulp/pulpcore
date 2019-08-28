from rest_framework import pagination


class NamePagination(pagination.PageNumberPagination):
    """
    Paginate an API view based on the value of the 'name' field of objects being iterated over.

    This Paginator should be used for any model that has a 'name' field and requires a value,
    allowing for a more obvious and user-friendly pagination than the default by-id pagination.

    """
    ordering = 'name'
    page_size_query_param = 'page_size'
    max_page_size = 5000
