from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class AdminPagination(PageNumberPagination):
    page_size = 25
    page_query_param = 'page'
    page_size_query_param = 'page_size'

    def get_paginated_response(self, data):
        return Response(
            {
                'data': data,
                'meta': {
                    'page': self.page.number,
                    'page_size': self.get_page_size(self.request),
                    'total': self.page.paginator.count,
                },
            }
        )
