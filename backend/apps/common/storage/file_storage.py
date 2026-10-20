"""Hash based file storage helpers with de-duplication."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.common.api.api_exception_handler import BusinessError

CHUNK_SIZE = 64 * 1024


def sha256_of(fileobj) -> str:
    """Compute sha256 of a Django UploadedFile / file-like object."""
    digest = hashlib.sha256()
    if hasattr(fileobj, "seek"):
        fileobj.seek(0)
    for chunk in iter(lambda: fileobj.read(CHUNK_SIZE), b""):
        digest.update(chunk)
    if hasattr(fileobj, "seek"):
        fileobj.seek(0)
    return digest.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_path_for(name: str, sha: str, subdir: str = "uploads") -> str:
    suffix = Path(name).suffix.lower()[:10]
    return f"{subdir}/{sha[:2]}/{sha}{suffix}"


def save_bytes(data: bytes, filename: str, subdir: str = "uploads") -> tuple[str, str, int]:
    """Persist ``data`` and return ``(stored_path, sha256, size)``."""
    sha = sha256_of_bytes(data)
    path = storage_path_for(filename, sha, subdir)
    if not default_storage.exists(path):
        default_storage.save(path, ContentFile(data))
    return path, sha, len(data)


def save_uploaded_file(uploaded_file, subdir: str = "uploads") -> tuple[str, str, int]:
    """Persist an ``UploadedFile``; identical content is stored once."""
    if uploaded_file is None:
        raise BusinessError(message="未提供文件", code="missing_file")
    if uploaded_file.size == 0:
        raise BusinessError(message="文件内容为空", code="empty_file")
    max_bytes = getattr(settings, "FILE_UPLOAD_MAX_MEMORY_SIZE", 20 * 1024 * 1024)
    if uploaded_file.size > max_bytes:
        raise BusinessError(message="文件超过大小限制", code="file_too_large")

    sha = sha256_of(uploaded_file)
    path = storage_path_for(uploaded_file.name, sha, subdir)
    if not default_storage.exists(path):
        uploaded_file.seek(0)
        default_storage.save(path, uploaded_file)
    return path, sha, uploaded_file.size


def guess_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def absolute_media_path(relative_path: str) -> Path:
    return Path(settings.MEDIA_ROOT) / relative_path


def delete_media(relative_path: str) -> None:
    try:
        if relative_path and default_storage.exists(relative_path):
            default_storage.delete(relative_path)
    except OSError:
        pass


def make_run_dir(prefix: str) -> Path:
    """Create a unique directory under MEDIA_ROOT for execution artefacts."""
    safe_prefix = "".join(c for c in prefix if c.isalnum() or c in "-_")[:40] or "run"
    path = Path(settings.MEDIA_ROOT) / safe_prefix / uuid.uuid4().hex[:12]
    os.makedirs(path, exist_ok=True)
    return path
