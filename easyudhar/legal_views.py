from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from adminapp.models import LegalDocument
from adminapp.services.legal import get_published_legal_document, legal_document_to_dict


class PublicLegalDocumentListView(APIView):
    """List published legal documents (no auth)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        docs = LegalDocument.objects.filter(is_published=True).order_by('slug')
        return Response(
            {
                'data': [
                    legal_document_to_dict(doc, include_body=False)
                    for doc in docs
                ],
            }
        )


class PublicLegalDocumentDetailView(APIView):
    """Fetch a published legal document by slug (no auth)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        doc = get_published_legal_document(slug)
        if not doc:
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(legal_document_to_dict(doc))
