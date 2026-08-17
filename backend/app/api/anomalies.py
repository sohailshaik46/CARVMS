from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.models.user import User
from app.schemas.anomaly import AnomalyDismissRequest, AnomalyOut, AnomalyScanRequest
from app.services import anomaly_service, dataset_service
from app.services.anomaly_service import RuleConfigError

router = APIRouter(tags=["Forensic Anomalies"])


@router.post("/datasets/{dataset_id}/anomaly-scan", response_model=list[AnomalyOut], status_code=201)
def scan_dataset(
    dataset_id: int,
    payload: AnomalyScanRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dataset = dataset_service.get_dataset(db, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        return anomaly_service.scan_dataset(
            db,
            dataset=dataset,
            rules=payload.rules,
            repeated_value_column=payload.repeated_value_column,
            repeated_value_threshold=payload.repeated_value_threshold,
            outlier_column=payload.outlier_column,
            outlier_iqr_multiplier=payload.outlier_iqr_multiplier,
            actor=user,
        )
    except RuleConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/datasets/{dataset_id}/anomalies", response_model=list[AnomalyOut])
def list_anomalies(
    dataset_id: int,
    status: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return anomaly_service.list_anomalies(db, dataset_id=dataset_id, status=status)


@router.get("/anomalies/{anomaly_id}", response_model=AnomalyOut)
def get_anomaly(
    anomaly_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    anomaly = anomaly_service.get_anomaly(db, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return anomaly


@router.post("/anomalies/{anomaly_id}/dismiss", response_model=AnomalyOut)
def dismiss_anomaly(
    anomaly_id: int,
    payload: AnomalyDismissRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    anomaly = anomaly_service.get_anomaly(db, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return anomaly_service.dismiss_anomaly(db, anomaly=anomaly, reason=payload.reason, actor=user)
