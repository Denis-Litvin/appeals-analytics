from rest_framework.pagination import PageNumberPagination


class Pagination(PageNumberPagination):
    """По 50 записей, размер страницы можно задать параметром page_size, но не больше 500."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
