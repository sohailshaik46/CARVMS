from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.models.user import User
from app.schemas.dataset import DatasetColumnOut, DatasetOut
from app.services import dataset_service

router = APIRouter(prefix="/datasets", tags=["Datasets"])


def _get_dataset_or_404(db: Session, dataset_id: int):
    dataset = dataset_service.get_dataset(db, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


def _authorize_manage(user: User, dataset) -> None:
    if user.role == roles.ADMIN or dataset.uploaded_by_id == user.id:
        return
    raise HTTPException(status_code=403, detail="Not permitted to manage this dataset")


@router.post("", response_model=DatasetOut, status_code=201)
def upload_dataset(
    name: str = Form(...),
    lineage_of_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return dataset_service.upload_dataset(
        db, upload_file=file, name=name, uploader=user, lineage_of_id=lineage_of_id
    )


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return dataset_service.list_datasets(db, status=status, skip=skip, limit=limit)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return _get_dataset_or_404(db, dataset_id)


@router.get("/{dataset_id}/columns", response_model=list[DatasetColumnOut])
def list_columns(
    dataset_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _get_dataset_or_404(db, dataset_id)
    return dataset_service.list_columns(db, dataset_id)


@router.post("/{dataset_id}/reprocess", response_model=DatasetOut)
def reprocess_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset = _get_dataset_or_404(db, dataset_id)
    _authorize_manage(user, dataset)
    return dataset_service.reprocess_dataset(db, dataset=dataset, actor=user)


@router.post("/{dataset_id}/archive", response_model=DatasetOut)
def archive_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset = _get_dataset_or_404(db, dataset_id)
    _authorize_manage(user, dataset)
    return dataset_service.archive_dataset(db, dataset=dataset, actor=user)
