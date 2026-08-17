from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.models.user import User
from app.schemas.reconciliation import (
    ReconciliationCreate,
    ReconciliationDetailOut,
    ReconciliationOut,
)
from app.services import dataset_service, reconciliation_service
from app.services.reconciliation_service import ColumnNotFoundError, NotProfilableError

router = APIRouter(prefix="/reconciliations", tags=["Reconciliation"])


@router.post("", response_model=ReconciliationDetailOut, status_code=201)
def create_reconciliation(
    payload: ReconciliationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset_a = dataset_service.get_dataset(db, payload.dataset_a_id)
    if dataset_a is None:
        raise HTTPException(status_code=404, detail="dataset_a not found")
    dataset_b = dataset_service.get_dataset(db, payload.dataset_b_id)
    if dataset_b is None:
        raise HTTPException(status_code=404, detail="dataset_b not found")

    try:
        return reconciliation_service.run_reconciliation(
            db,
            dataset_a=dataset_a,
            dataset_b=dataset_b,
            key_column_a=payload.key_column_a,
            key_column_b=payload.key_column_b,
            compare_columns=payload.compare_columns,
            actor=user,
        )
    except (NotProfilableError, ColumnNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[ReconciliationOut])
def list_reconciliations(
    dataset_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return reconciliation_service.list_reconciliations(db, dataset_id=dataset_id)


@router.get("/{reconciliation_id}", response_model=ReconciliationDetailOut)
def get_reconciliation(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    recon = reconciliation_service.get_reconciliation(db, reconciliation_id)
    if recon is None:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    return recon
