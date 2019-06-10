from rest_framework import pagination


class IDPagination(pagination.PageNumberPagination):
    """
    Paginate an API view naively, based on the ID of objects being iterated over.

    This assumes that the objects being iterated over have an 'id' field, that the value of this
    field is a int, and that the field is indexed.

    This assumption should be True for all Models inheriting `pulpcore.app.models.Model`, the Pulp
    base Model class.

    """

    ordering = "id"
    page_size_query_param = "page_size"
    max_page_size = 5000


class NamePagination(pagination.PageNumberPagination):
    """
    Paginate an API view based on the value of the 'name' field of objects being iterated over.

    This Paginator should be used for any model that has a 'name' field and requires a value,
    allowing for a more obvious and user-friendly pagination than the default by-id pagination.

    """

    ordering = "name"
    page_size_query_param = "page_size"
    max_page_size = 5000
