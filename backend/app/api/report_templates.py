from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.reports import VIGILANCE_ROLES, export_response, filters_from_dict
from app.auth.dependencies import require_role
from app.database.database import get_db
from app.models.user import User
from app.schemas.report import ReportHistoryOut, ReportTemplateCreate, ReportTemplateOut
from app.services import report_service

router = APIRouter(tags=["Report Templates & History"])


@router.post("/report-templates", response_model=ReportTemplateOut, status_code=201)
def create_template(
    payload: ReportTemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return report_service.create_template(
        db,
        name=payload.name,
        description=payload.description,
        filters=payload.filters.model_dump(mode="json"),
        creator=user,
    )


@router.get("/report-templates", response_model=list[ReportTemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return report_service.list_templates(db)


@router.get("/report-templates/{template_id}", response_model=ReportTemplateOut)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    template = report_service.get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Report template not found")
    return template


@router.delete("/report-templates/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    template = report_service.get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Report template not found")
    try:
        report_service.delete_template(db, template=template, actor=user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/report-templates/{template_id}/run")
def run_template(
    template_id: int,
    format: str = Query(pattern="^(csv|xlsx|pdf|docx|pptx)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Runs a saved template's filters through the live Metric Engine right
    now -- never replays a stored result. Same filters, run today vs. run
    last month, will differ only if the underlying data differs; the
    calculation itself is identical to what the dashboard would show."""
    template = report_service.get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Report template not found")

    filters = filters_from_dict(template.filters)
    return export_response(db, user, filters, format, name=template.name, template_id=template.id)


@router.get("/report-history", response_model=list[ReportHistoryOut])
def list_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    return report_service.list_history(db, skip=skip, limit=limit)


@router.get("/report-history/{history_id}", response_model=ReportHistoryOut)
def get_history(
    history_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    entry = report_service.get_history(db, history_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Report history entry not found")
    return entry


@router.post("/report-history/{history_id}/regenerate")
def regenerate(
    history_id: int,
    format: str | None = Query(default=None, pattern="^(csv|xlsx|pdf|docx|pptx)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(*VIGILANCE_ROLES)),
):
    """Re-runs a past report's exact filters against live data -- this is
    NOT re-downloading a stored file (none exists). If the underlying
    audits/findings changed since the original run, the regenerated numbers
    will reflect that; they are never a stale snapshot passed off as current.
    """
    entry = report_service.get_history(db, history_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Report history entry not found")

    fmt = format or entry.format
    filters = filters_from_dict(entry.filters_used)
    return export_response(
        db, user, filters, fmt, name=entry.name, template_id=entry.template_id, regenerated_from_id=entry.id
    )
