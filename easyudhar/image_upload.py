"""Resize and compress uploaded images before saving to MEDIA_ROOT."""

import io
import os
import uuid

from django.conf import settings
from django.core.files.base import ContentFile

_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.heic', '.heif'}


def _is_image_upload(upload):
    name = (getattr(upload, 'name', '') or '').lower()
    ext = os.path.splitext(name)[1]
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    return ext in _IMAGE_EXTENSIONS or content_type.startswith('image/')


def _safe_jpeg_name(original_name):
    base = os.path.splitext(os.path.basename(original_name or ''))[0]
    base = ''.join(c for c in base if c.isalnum() or c in ('-', '_')).strip()[:60]
    if not base:
        base = uuid.uuid4().hex[:12]
    return f'{base}.jpg'


def _encode_jpeg(image, *, quality):
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', optimize=True, quality=quality)
    return buffer.getvalue()


def _fit_under_byte_limit(image, *, max_bytes, max_dim, start_quality, min_quality, min_dim):
    """Shrink dimensions and/or JPEG quality until image data fits max_bytes."""
    from PIL import Image

    best = None
    dim = min(max_dim, max(image.size))

    while dim >= min_dim:
        frame = image.copy()
        if max(frame.size) > dim:
            frame.thumbnail((dim, dim), Image.Resampling.LANCZOS)

        quality = start_quality
        while quality >= min_quality:
            data = _encode_jpeg(frame, quality=quality)
            best = data
            if len(data) <= max_bytes:
                return data
            quality -= 5

        dim = int(dim * 0.85)

    return best or _encode_jpeg(image, quality=min_quality)


def compress_uploaded_image(upload):
    """
    Normalize every image upload to JPEG with fixed server rules:
    - Longest side <= IMAGE_UPLOAD_MAX_DIMENSION (default 1024px)
    - File size <= IMAGE_UPLOAD_MAX_BYTES (default 64KB)
    - Same format (.jpg) for all chat / bill images

    Smaller images are not upscaled. Non-images pass through unchanged.
  """
    if upload is None:
        return None
    if not _is_image_upload(upload):
        return upload

    max_dim = getattr(settings, 'IMAGE_UPLOAD_MAX_DIMENSION', 1024)
    quality = getattr(settings, 'IMAGE_UPLOAD_JPEG_QUALITY', 75)
    max_bytes = getattr(settings, 'IMAGE_UPLOAD_MAX_BYTES', 64 * 1024)
    min_quality = getattr(settings, 'IMAGE_UPLOAD_MIN_JPEG_QUALITY', 35)
    min_dim = getattr(settings, 'IMAGE_UPLOAD_MIN_DIMENSION', 480)

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return upload

    try:
        upload.seek(0)
        image = Image.open(upload)
        image.load()
    except Exception:
        upload.seek(0)
        return upload

    if getattr(image, 'is_animated', False) and getattr(image, 'n_frames', 1) > 1:
        upload.seek(0)
        return upload

    image = ImageOps.exif_transpose(image)

    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    elif image.mode == 'P':
        image = image.convert('RGB')
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    data = _fit_under_byte_limit(
        image,
        max_bytes=max_bytes,
        max_dim=max_dim,
        start_quality=quality,
        min_quality=min_quality,
        min_dim=min_dim,
    )

    return ContentFile(data, name=_safe_jpeg_name(getattr(upload, 'name', '')))
