from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import roles
from app.auth.dependencies import require_role
from app.database.database import get_db
from app.models.user import User
from app.schemas.search import SearchResponse
from app.services.search_service import SEARCHABLE_TYPES, global_search

router = APIRouter(tags=["Search"])

VIGILANCE_ROLES = (roles.ADMIN, roles.AUDITOR)


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1),
    types: str | None = Query(default=None, description="Comma-separated subset of: " + ", ".join(SEARCHABLE_TYPES)),
    limit_per_type: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    type_list = [t.strip() for t in types.split(",")] if types else None
    results = global_search(db, user, q, types=type_list, limit_per_type=limit_per_type)
    total = sum(len(v) for v in results.values())
    return {"query": q, "results": results, "total": total}
