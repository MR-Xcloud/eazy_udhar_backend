from ..models import LegalDocument


def legal_document_to_dict(doc, *, include_body=True):
    data = {
        'id': doc.pk,
        'slug': doc.slug,
        'title': doc.title,
        'version': doc.version,
        'effective_date': doc.effective_date.isoformat() if doc.effective_date else None,
        'is_published': doc.is_published,
        'updated_at': doc.updated_at.isoformat(),
    }
    if include_body:
        data['body'] = doc.body
    return data


def get_published_legal_document(slug):
    return LegalDocument.objects.filter(slug=slug, is_published=True).first()
