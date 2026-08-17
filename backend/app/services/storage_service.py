"""File storage abstraction. Originals live on disk under settings.UPLOAD_DIR;
the DB only ever stores metadata (path/checksum/size) -- never blob bytes.
Swapping to S3-compatible storage later means changing this module only.
"""
import hashlib
import os
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile

from app.config import settings


@dataclass
class SavedFile:
    storage_path: str  # relative to UPLOAD_DIR, stored in the DB
    absolute_path: str
    size_bytes: int
    checksum: str


def validate_upload(upload_file: UploadFile) -> None:
    content_type = upload_file.content_type or "application/octet-stream"
    if content_type not in settings.allowed_upload_mime_types_set:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{content_type}' is not permitted",
        )


def save_upload(upload_file: UploadFile, subdir: str) -> SavedFile:
    """Reads the whole upload into memory to hash+size-check it, then writes
    it once. Fine for the file sizes this app allows (MAX_UPLOAD_SIZE_MB);
    a genuinely large-file path would stream-hash instead."""
    validate_upload(upload_file)

    raw = upload_file.file.read()
    size_bytes = len(raw)
    if size_bytes > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB upload limit",
        )
    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    checksum = hashlib.sha256(raw).hexdigest()

    safe_original_name = os.path.basename(upload_file.filename or "upload.bin")
    stored_name = f"{uuid.uuid4().hex}_{safe_original_name}"

    target_dir = os.path.join(settings.UPLOAD_DIR, subdir)
    os.makedirs(target_dir, exist_ok=True)

    relative_path = os.path.join(subdir, stored_name)
    absolute_path = os.path.join(settings.UPLOAD_DIR, relative_path)

    with open(absolute_path, "wb") as f:
        f.write(raw)

    return SavedFile(
        storage_path=relative_path.replace("\\", "/"),
        absolute_path=absolute_path,
        size_bytes=size_bytes,
        checksum=checksum,
    )


def absolute_path_for(storage_path: str) -> str:
    return os.path.join(settings.UPLOAD_DIR, storage_path)


def delete_file_if_exists(storage_path: str) -> None:
    """Best-effort cleanup for batch deletion -- the DB row referencing
    this file is being removed regardless, so a file that's already
    missing (or a permissions hiccup) is not a reason to fail the whole
    delete."""
    try:
        os.remove(absolute_path_for(storage_path))
    except OSError:
        pass
