from rest_framework import status
from rest_framework.response import Response

from ..models import AdminUser, LegalDocument
from ..permissions import RoleRequired
from ..services.legal import legal_document_to_dict
from ..utils import log_audit
from .base import AdminAPIView


class LegalDocumentListView(AdminAPIView):
    def get(self, request):
        docs = LegalDocument.objects.all().order_by('slug')
        return Response({'data': [legal_document_to_dict(doc) for doc in docs]})

    def get_permissions(self):
        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method == 'POST':
            perms.append(RoleRequired([AdminUser.ROLE_SUPER_ADMIN]))
        return perms

    def post(self, request):
        slug = (request.data.get('slug') or '').strip()
        title = (request.data.get('title') or '').strip()
        body = (request.data.get('body') or '').strip()
        if not slug:
            return Response({'detail': 'Slug is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not title:
            return Response({'detail': 'Title is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not body:
            return Response({'detail': 'Body is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if LegalDocument.objects.filter(slug=slug).exists():
            return Response({'detail': 'Slug already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        doc = LegalDocument.objects.create(
            slug=slug,
            title=title,
            body=body,
            version=(request.data.get('version') or '1.0').strip() or '1.0',
            effective_date=request.data.get('effective_date') or None,
            is_published=bool(request.data.get('is_published', True)),
        )
        log_audit(request.user, 'legal_document_create', 'legal_document', doc.pk, request=request)
        return Response(legal_document_to_dict(doc), status=status.HTTP_201_CREATED)


class LegalDocumentDetailView(AdminAPIView):
    def get_permissions(self):
        perms = [perm() for perm in AdminAPIView.permission_classes]
        if self.request.method in ('PATCH', 'DELETE'):
            perms.append(RoleRequired([AdminUser.ROLE_SUPER_ADMIN]))
        return perms

    def get(self, request, pk):
        try:
            doc = LegalDocument.objects.get(pk=pk)
        except LegalDocument.DoesNotExist:
            return Response({'detail': 'Legal document not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(legal_document_to_dict(doc))

    def patch(self, request, pk):
        try:
            doc = LegalDocument.objects.get(pk=pk)
        except LegalDocument.DoesNotExist:
            return Response({'detail': 'Legal document not found.'}, status=status.HTTP_404_NOT_FOUND)

        if 'slug' in request.data:
            slug = (request.data.get('slug') or '').strip()
            if not slug:
                return Response({'detail': 'Slug cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
            if LegalDocument.objects.exclude(pk=pk).filter(slug=slug).exists():
                return Response({'detail': 'Slug already exists.'}, status=status.HTTP_400_BAD_REQUEST)
            doc.slug = slug
        if 'title' in request.data:
            title = (request.data.get('title') or '').strip()
            if not title:
                return Response({'detail': 'Title cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
            doc.title = title
        if 'body' in request.data:
            body = (request.data.get('body') or '').strip()
            if not body:
                return Response({'detail': 'Body cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
            doc.body = body
        if 'version' in request.data:
            doc.version = (request.data.get('version') or '1.0').strip() or '1.0'
        if 'effective_date' in request.data:
            doc.effective_date = request.data.get('effective_date') or None
        if 'is_published' in request.data:
            doc.is_published = bool(request.data['is_published'])

        doc.save()
        log_audit(request.user, 'legal_document_update', 'legal_document', doc.pk, request=request)
        return Response(legal_document_to_dict(doc))

    def delete(self, request, pk):
        try:
            doc = LegalDocument.objects.get(pk=pk)
        except LegalDocument.DoesNotExist:
            return Response({'detail': 'Legal document not found.'}, status=status.HTTP_404_NOT_FOUND)
        doc.is_published = False
        doc.save(update_fields=['is_published', 'updated_at'])
        log_audit(request.user, 'legal_document_unpublish', 'legal_document', doc.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
