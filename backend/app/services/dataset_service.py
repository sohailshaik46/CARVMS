from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.dataset import PROFILABLE_SOURCE_TYPES, Dataset, DatasetColumn
from app.models.user import User
from app.services import audit_log_service, profiling_service, storage_service

_EXTENSION_TO_SOURCE_TYPE = {
    ".csv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".pdf": "pdf",
    ".docx": "word",
    ".pptx": "pptx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}


class UnsupportedFileTypeError(Exception):
    pass


def _infer_source_type(filename: str) -> str:
    import os

    ext = os.path.splitext(filename)[1].lower()
    source_type = _EXTENSION_TO_SOURCE_TYPE.get(ext)
    if source_type is None:
        raise UnsupportedFileTypeError(f"Unsupported file extension '{ext}'")
    return source_type


def _run_profiling(db: Session, dataset: Dataset) -> None:
    """Mutates dataset in place; does not commit -- caller controls the
    transaction so a failed profile and the initial insert stay atomic."""
    if dataset.source_type not in PROFILABLE_SOURCE_TYPES:
        # Honest, not silent: this is a real, final state for non-tabular
        # uploads, not a placeholder waiting to be "finished" later.
        dataset.status = "uploaded"
        return

    dataset.status = "profiling"
    try:
        abs_path = storage_service.absolute_path_for(dataset.storage_path)
        df = profiling_service.load_dataframe(abs_path, dataset.source_type)
        result = profiling_service.profile_dataframe(df, db)
    except Exception as exc:  # noqa: BLE001 -- malformed upload is a data problem, not a bug
        dataset.status = "failed"
        dataset.profiling_error = str(exc)[:500]
        return

    dataset.row_count = result.row_count
    dataset.column_count = result.column_count
    dataset.duplicate_row_count = result.duplicate_row_count
    dataset.quality_score = result.quality_score
    dataset.status = "clean"
    dataset.profiling_error = None

    for col in result.columns:
        db.add(
            DatasetColumn(
                dataset_id=dataset.id,
                name=col.name,
                inferred_type=col.inferred_type,
                null_rate=col.null_rate,
                mapped_dimension=col.mapped_dimension,
            )
        )


def upload_dataset(
    db: Session,
    *,
    upload_file: UploadFile,
    name: str,
    uploader: User,
    lineage_of_id: Optional[int] = None,
) -> Dataset:
    try:
        source_type = _infer_source_type(upload_file.filename or "")
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc))

    saved = storage_service.save_upload(upload_file, subdir="datasets")

    version = 1
    if lineage_of_id is not None:
        parent = get_dataset(db, lineage_of_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="lineage_of dataset not found")
        version = parent.version + 1

    dataset = Dataset(
        name=name,
        source_type=source_type,
        original_filename=upload_file.filename or "upload.bin",
        storage_path=saved.storage_path,
        checksum=saved.checksum,
        uploaded_by_id=uploader.id,
        version=version,
        status="uploaded",
        lineage_of_id=lineage_of_id,
    )
    db.add(dataset)
    db.flush()

    _run_profiling(db, dataset)
    db.flush()

    audit_log_service.record(
        db,
        actor=uploader,
        action="dataset.uploaded",
        entity_type="Dataset",
        entity_id=dataset.id,
        after={
            "name": name,
            "source_type": source_type,
            "status": dataset.status,
            "row_count": dataset.row_count,
        },
    )
    db.commit()
    db.refresh(dataset)
    return dataset


def get_dataset(db: Session, dataset_id: int) -> Optional[Dataset]:
    return db.query(Dataset).filter(Dataset.id == dataset_id).first()


def list_datasets(
    db: Session, *, status: Optional[str] = None, skip: int = 0, limit: int = 50
) -> list[Dataset]:
    query = db.query(Dataset)
    if status is not None:
        query = query.filter(Dataset.status == status)
    limit = max(1, min(limit, 200))
    return query.order_by(Dataset.id.desc()).offset(max(0, skip)).limit(limit).all()


def list_columns(db: Session, dataset_id: int) -> list[DatasetColumn]:
    return db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset_id).all()


def reprocess_dataset(db: Session, *, dataset: Dataset, actor: User) -> Dataset:
    db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset.id).delete()
    _run_profiling(db, dataset)
    db.flush()

    audit_log_service.record(
        db,
        actor=actor,
        action="dataset.reprocessed",
        entity_type="Dataset",
        entity_id=dataset.id,
        after={"status": dataset.status, "row_count": dataset.row_count},
    )
    db.commit()
    db.refresh(dataset)
    return dataset


def archive_dataset(db: Session, *, dataset: Dataset, actor: User) -> Dataset:
    before_status = dataset.status
    dataset.status = "archived"
    db.flush()

    audit_log_service.record(
        db,
        actor=actor,
        action="dataset.archived",
        entity_type="Dataset",
        entity_id=dataset.id,
        before={"status": before_status},
        after={"status": "archived"},
    )
    db.commit()
    db.refresh(dataset)
    return dataset
