from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.database.database import get_db
from app.models.user import User
from app.schemas.center_scoring import CenterRankingOut, CenterScoringWeightOut, CenterScoringWeightUpdate
from app.services import center_scoring_service
from app.services.metrics import MetricFilters

router = APIRouter(tags=["Center Performance Scoring"])

VIGILANCE_ROLES = (roles.ADMIN, roles.AUDITOR)


@router.get("/center-scoring/weights", response_model=list[CenterScoringWeightOut])
def list_weights(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return center_scoring_service.list_weights(db)


@router.patch("/center-scoring/weights/{component_key}", response_model=CenterScoringWeightOut)
def update_weight(
    component_key: str,
    payload: CenterScoringWeightUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(roles.ADMIN)),
):
    weight_row = center_scoring_service.get_weight(db, component_key)
    if weight_row is None:
        raise HTTPException(status_code=404, detail="Unknown scoring component")
    return center_scoring_service.update_weight(db, weight_row=weight_row, new_weight=payload.weight, actor=admin)


@router.get("/center-scoring/rankings", response_model=list[CenterRankingOut])
def get_rankings(
    period_from: date | None = None,
    period_to: date | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    filters = MetricFilters(period_from=period_from, period_to=period_to)
    return center_scoring_service.compute_rankings(db, filters)
